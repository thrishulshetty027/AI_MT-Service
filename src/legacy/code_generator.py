import os
import re
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from src.ir_models import FunctionSignature, Parameter
from src.type_resolver import ResolvedTestCase


_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

_SIMPLE_C_TYPES = {
    "int", "float", "double", "char", "long", "short",
    "unsigned int", "unsigned char", "unsigned long",
    "signed int", "signed char", "signed long",
    "int[]", "float[]", "double[]", "char[]",
    "char*", "int*", "float*", "double*", "void*",
    "FILE*",
}

_DECLARATION_PROMPT = """You are a C test code generator for Cantata++.
Generate ONLY the C variable declarations and function call for this test case.

FUNCTION SIGNATURE:
{return_type} {function_name}({param_list});

PARAMETERS:
{param_details}

TEST CASE DATA:
{test_data}

RULES:
1. Declare each variable before use, at block start (C89 compatible)
2. Arrays use brace init: int arr[] = {1,2,3};
3. Char arrays: char dest[20] = "";
4. Char pointers: char* src = "hello";
5. Structs: initialize every field — struct Point p = {.x=1, .y=2};
6. Enums: enum Status s = OK;
7. Function pointers: int (*fn)(int) = helper;
8. 2D arrays: int mat[2][3] = {{1,2,3},{4,5,6}};
9. Function call uses variable names only: func(arr, size) — NEVER func(arr[])
10. If return type is void, do NOT assign result. Just call the function.
11. If return type is non-void, assign to: {return_type} result = func(...);

OUTPUT FORMAT — emit exactly two sections:

DECLARATIONS:
<one declaration per line, each ending with semicolon>

CALL:
<single function call line ending with semicolon>
"""


def _is_simple_type(c_type: str) -> bool:
    return c_type in _SIMPLE_C_TYPES


def _needs_llm_fallback(tc: ResolvedTestCase) -> bool:
    if not tc.signature:
        return False
    for p in tc.signature.parameters:
        if not _is_simple_type(p.c_type):
            return True
    for var_name, c_type in tc.resolved_types.items():
        if c_type == "unknown" and var_name not in ("expected_result", "return_value"):
            return True
    return False


def _format_parameter_declarations(sig: FunctionSignature) -> str:
    parts = []
    for p in sig.parameters:
        if p.c_type.endswith("[]"):
            parts.append(f"{p.base_type} {p.name}[]")
        elif p.c_type.endswith("*"):
            parts.append(f"{p.c_type} {p.name}")
        else:
            parts.append(f"{p.c_type} {p.name}")
    return ", ".join(parts) if parts else "void"


def _is_array_type(c_type: str) -> bool:
    return c_type.endswith("[]")


def _is_pointer_type(c_type: str) -> bool:
    return c_type.endswith("*")


def _declaration_for_var(var_name: str, c_type: str, value: str) -> str:
    if _is_array_type(c_type):
        return f"{c_type.replace('[]', '')} {var_name}[] = {value}"
    elif _is_pointer_type(c_type):
        return f"{c_type} {var_name} = {value}"
    else:
        return f"{c_type} {var_name} = {value}"


def _extract_numeric_expected(expected_result: str) -> str | None:
    if not expected_result:
        return None
    patterns = [
        r"equals\s+([-\d]+)",
        r"==\s*([-\d]+)",
        r"return\s*value\s*([-\d]+)",
        r"([-\d]+)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, expected_result, re.IGNORECASE)
        if m:
            return m.group(1)
    if expected_result.lstrip("-").isdigit():
        return expected_result
    return None


def _call_llm_for_declarations(tc: ResolvedTestCase) -> tuple[list[str], str]:
    from glm_client import call_glm_4_7_flash

    sig = tc.signature
    param_list = ", ".join(
        f"{p.c_type} {p.name}" for p in sig.parameters
    ) if sig.parameters else "void"

    param_details = "\n".join(
        f"  {p.c_type} {p.name}" for p in sig.parameters
    )

    data_lines = []
    for k, v in tc.input_values.items():
        c_type = tc.resolved_types.get(k, "unknown")
        data_lines.append(f"  {k} ({c_type}) = {v}")
    test_data = "\n".join(data_lines)

    prompt = _DECLARATION_PROMPT.format(
        return_type=sig.return_type,
        function_name=sig.name,
        param_list=param_list,
        param_details=param_details,
        test_data=test_data,
    )

    response = call_glm_4_7_flash(prompt)

    declarations = []
    call_line = ""

    in_declarations = False
    in_call = False
    for line in response.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("DECLARATIONS"):
            in_declarations = True
            in_call = False
            continue
        if stripped.upper().startswith("CALL"):
            in_declarations = False
            in_call = True
            continue
        if in_declarations and stripped and not stripped.startswith("//"):
            if not stripped.endswith(";"):
                stripped += ";"
            declarations.append(stripped)
        elif in_call and stripped and not stripped.startswith("//"):
            if not stripped.endswith(";"):
                stripped += ";"
            call_line = stripped
            in_call = False

    return declarations, call_line


def _parse_llm_call_args(call_line: str) -> str:
    m = re.search(r'(\w+)\s*\(([^)]*)\)', call_line)
    if m:
        return m.group(2).strip()
    return ""


def _prepare_simple_test_case(tc: ResolvedTestCase, index: int) -> dict:
    sig = tc.signature
    test_func_name = f"test_{tc.function_name}_{index:03d}"

    variables = []
    call_args = []

    param_order = [p.name for p in sig.parameters] if sig else list(tc.input_values.keys())

    used_param_names = set()

    for param_name in param_order:
        best_var = None
        best_c_type = None

        for var_name, var_value in tc.input_values.items():
            if var_name in used_param_names:
                continue

            resolved_type = tc.resolved_types.get(var_name, "unknown")

            if var_name == param_name:
                best_var = var_name
                best_c_type = resolved_type
                break

        if best_var is None:
            for var_name, var_value in tc.input_values.items():
                if var_name in used_param_names:
                    continue
                if var_name.startswith(param_name) or var_name.endswith(param_name):
                    best_var = var_name
                    best_c_type = tc.resolved_types.get(var_name, "unknown")
                    break

        if best_var is None:
            continue

        used_param_names.add(best_var)
        var_value = tc.input_values[best_var]
        c_type = best_c_type if best_c_type != "unknown" else "int"

        if best_var in tc.declarations:
            raw_decl = tc.declarations[best_var]
            variables.append({
                "name": best_var,
                "c_type": c_type,
                "value": var_value,
                "declaration": raw_decl,
            })
        else:
            variables.append({
                "name": best_var,
                "c_type": c_type,
                "value": var_value,
                "declaration": _declaration_for_var(best_var, c_type, var_value),
            })
        call_args.append(best_var)

    state_checks = []
    if tc.return_type == "void":
        for var_name, var_value in tc.input_values.items():
            if var_name.startswith("expected_"):
                actual_name = var_name[len("expected_"):]
                state_checks.append(f"CHECK_EQUAL({var_value}, {actual_name})")

    expected_c_expr = _extract_numeric_expected(tc.expected_result)
    if expected_c_expr is None:
        if "expected_result" in tc.input_values:
            expected_c_expr = tc.input_values["expected_result"]
        else:
            expected_c_expr = tc.expected_result

    return {
        "test_id": tc.test_id,
        "test_function_name": test_func_name,
        "function_name": tc.function_name,
        "scenario": tc.scenario,
        "return_type": tc.return_type,
        "variables": variables,
        "call_arguments": ", ".join(call_args),
        "expected_c_expression": expected_c_expr,
        "state_checks": state_checks,
        "test_type": tc.test_type,
        "used_llm": False,
    }


def _prepare_llm_test_case(tc: ResolvedTestCase, index: int) -> dict:
    sig = tc.signature
    test_func_name = f"test_{tc.function_name}_{index:03d}"

    declarations, call_line = _call_llm_for_declarations(tc)

    call_args_str = _parse_llm_call_args(call_line)

    variables = []
    for decl in declarations:
        name_match = re.search(r'(\w+)\s*(?:\[|;|=)', decl)
        var_name = name_match.group(1) if name_match else ""
        variables.append({
            "name": var_name,
            "c_type": "complex",
            "value": "",
            "declaration": decl,
        })

    expected_c_expr = _extract_numeric_expected(tc.expected_result)
    if expected_c_expr is None:
        if "expected_result" in tc.input_values:
            expected_c_expr = tc.input_values["expected_result"]
        else:
            expected_c_expr = tc.expected_result

    return {
        "test_id": tc.test_id,
        "test_function_name": test_func_name,
        "function_name": tc.function_name,
        "scenario": tc.scenario,
        "return_type": tc.return_type,
        "variables": variables,
        "call_arguments": call_args_str,
        "expected_c_expression": expected_c_expr,
        "state_checks": [],
        "test_type": tc.test_type,
        "used_llm": True,
    }


def _prepare_test_case_data(tc: ResolvedTestCase, index: int, use_llm: bool = True) -> dict:
    if use_llm and _needs_llm_fallback(tc):
        try:
            return _prepare_llm_test_case(tc, index)
        except Exception as e:
            print(f"  [WARN] LLM fallback failed for {tc.test_id}: {e}. Using template.")
            return _prepare_simple_test_case(tc, index)
    return _prepare_simple_test_case(tc, index)


def generate_test_script(
    test_cases: list[ResolvedTestCase],
    signatures: list[FunctionSignature],
    pr_number: str,
    module_name: str | None = None,
    use_llm: bool = True,
) -> str:
    if not module_name:
        module_name = f"module_{pr_number}"

    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )
    template = env.get_template("cantata_test.c.j2")

    sig_data = []
    for sig in signatures:
        sig_data.append({
            "name": sig.name,
            "return_type": sig.return_type,
            "parameter_declarations": _format_parameter_declarations(sig),
            "is_static": sig.is_static,
        })

    tc_data = []
    for i, tc in enumerate(test_cases, 1):
        tc_data.append(_prepare_test_case_data(tc, i, use_llm=use_llm))

    return template.render(
        module_name=module_name,
        pr_number=pr_number,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        signatures=sig_data,
        test_cases=tc_data,
    )


def generate_header_file(
    signatures: list[FunctionSignature],
    pr_number: str,
) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )
    template = env.get_template("cantata_header.h.j2")

    sig_data = []
    for sig in signatures:
        sig_data.append({
            "name": sig.name,
            "return_type": sig.return_type,
            "parameter_declarations": _format_parameter_declarations(sig),
            "is_static": sig.is_static,
        })

    return template.render(
        pr_number=pr_number,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        signatures=sig_data,
    )
