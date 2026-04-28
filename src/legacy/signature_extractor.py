import tree_sitter_c as tsc
import tree_sitter as ts
from src.ir_models import FunctionSignature, Parameter

C_LANGUAGE = ts.Language(tsc.language())


def _strip_diff_markers(diff_content: str) -> str:
    lines = diff_content.split("\n")
    cleaned = []
    for line in lines:
        if line.startswith("diff --git"):
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("-"):
            continue
        if line.startswith("+"):
            cleaned.append(line[1:])
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def _resolve_type_str(type_node, declarator_node) -> tuple[str, bool, bool, str]:
    is_pointer = False
    is_array = False
    base_type = type_node.text.decode() if type_node else "int"

    if declarator_node is None:
        return base_type, is_pointer, is_array, base_type

    decl_type = declarator_node.type

    if decl_type == "pointer_declarator":
        is_pointer = True
        c_type = base_type + "*"
        inner = declarator_node.child_by_field_name("declarator")
        if inner and inner.type == "array_declarator":
            is_array = True
            c_type = base_type + "*[]"
        return c_type, is_pointer, is_array, base_type

    if decl_type == "array_declarator":
        is_array = True
        c_type = base_type + "[]"
        return c_type, is_pointer, is_array, base_type

    return base_type, is_pointer, is_array, base_type


def _extract_return_type(func_node) -> tuple[str, bool]:
    type_node = func_node.child_by_field_name("type")
    declarator_node = func_node.child_by_field_name("declarator")

    if type_node is None:
        return "int", False

    return_type = type_node.text.decode()
    is_pointer_return = False

    if declarator_node and declarator_node.type == "pointer_declarator":
        is_pointer_return = True
        return_type = return_type + "*"
        inner = declarator_node.child_by_field_name("declarator")
        if inner and inner.type == "function_declarator":
            pass

    return return_type, is_pointer_return


def _extract_func_name(declarator_node) -> str:
    if declarator_node is None:
        return ""

    if declarator_node.type == "function_declarator":
        child = declarator_node.child_by_field_name("declarator")
        if child and child.type == "identifier":
            return child.text.decode()
        if child and child.type == "pointer_declarator":
            inner = child.child_by_field_name("declarator")
            if inner and inner.type == "identifier":
                return inner.text.decode()
        return ""

    if declarator_node.type == "pointer_declarator":
        inner = declarator_node.child_by_field_name("declarator")
        if inner and inner.type == "function_declarator":
            return _extract_func_name(inner)
        return ""

    return ""


def _extract_parameters(func_declarator_node) -> list[Parameter]:
    params = []
    if func_declarator_node is None:
        return params

    param_list = None
    for child in func_declarator_node.children:
        if child.type == "parameter_list":
            param_list = child
            break

    if param_list is None:
        return params

    for child in param_list.children:
        if child.type != "parameter_declaration":
            continue

        p_type_node = child.child_by_field_name("type")
        p_decl_node = child.child_by_field_name("declarator")

        p_base_type = p_type_node.text.decode() if p_type_node else "int"
        p_name = ""
        is_pointer = False
        is_array = False
        c_type = p_base_type

        if p_decl_node is None:
            params.append(Parameter(
                name=p_base_type,
                c_type=c_type,
                is_pointer=is_pointer,
                is_array=is_array,
                base_type=p_base_type,
            ))
            continue

        if p_decl_node.type == "identifier":
            p_name = p_decl_node.text.decode()
        elif p_decl_node.type == "pointer_declarator":
            is_pointer = True
            c_type = p_base_type + "*"
            inner = p_decl_node.child_by_field_name("declarator")
            if inner:
                if inner.type == "identifier":
                    p_name = inner.text.decode()
                elif inner.type == "array_declarator":
                    is_array = True
                    c_type = p_base_type + "*[]"
                    arr_inner = inner.child_by_field_name("declarator")
                    if arr_inner and arr_inner.type == "identifier":
                        p_name = arr_inner.text.decode()
        elif p_decl_node.type == "array_declarator":
            is_array = True
            c_type = p_base_type + "[]"
            inner = p_decl_node.child_by_field_name("declarator")
            if inner and inner.type == "identifier":
                p_name = inner.text.decode()

        if not p_name:
            p_name = p_base_type

        params.append(Parameter(
            name=p_name,
            c_type=c_type,
            is_pointer=is_pointer,
            is_array=is_array,
            base_type=p_base_type,
        ))

    return params


def extract_signatures(diff_content: str) -> list[FunctionSignature]:
    cleaned_code = _strip_diff_markers(diff_content)
    if not cleaned_code.strip():
        return []

    parser = ts.Parser(C_LANGUAGE)
    tree = parser.parse(cleaned_code.encode())

    signatures = []

    def _walk(node):
        if node.type == "function_definition":
            return_type, is_pointer_return = _extract_return_type(node)

            is_static = False
            for child in node.children:
                if child.type == "storage_class_specifier":
                    if child.text.decode() == "static":
                        is_static = True

            declarator = node.child_by_field_name("declarator")
            func_declarator = declarator
            if declarator and declarator.type == "pointer_declarator":
                func_declarator = declarator.child_by_field_name("declarator")

            func_name = _extract_func_name(declarator)

            if func_name == "main":
                return

            parameters = _extract_parameters(func_declarator)

            sig = FunctionSignature(
                name=func_name,
                return_type=return_type,
                is_pointer_return=is_pointer_return,
                is_static=is_static,
                parameters=parameters,
            )
            signatures.append(sig)
            return

        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return signatures
