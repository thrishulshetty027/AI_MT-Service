"""
Stage 2 Generator — deterministic C code generation via Jinja2 templates.

Loads testcases.json, validates schema, resolves types, builds IR
(intermediate representation), and renders .c and .h files.
Zero LLM calls — fully deterministic.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import jinja2

from src.schemas import TestCaseFile, TestCase, FunctionMeta, StubConfig, TestType
from src.type_resolver import (
    CType,
    classify_parameter,
    get_zero_value,
    is_scalar,
    is_pointer_like,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
GENERATED_TESTS_DIR = "generated_tests"


def load_testcase_file(json_path: str) -> TestCaseFile:
    """
    Load and validate a testcases.json file.

    Args:
        json_path: Path to the testcases.json file

    Returns:
        Validated TestCaseFile

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or schema validation fails
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
    tc_file = TestCaseFile(**data)
    errors = tc_file.validate_internal_consistency()
    if errors:
        for err in errors:
            logger.warning("Consistency error: %s", err)
    return tc_file


def _resolve_c_type(c_type_str: str, typedef_map: Dict[str, str] = None) -> str:
    """Resolve a C type string to a canonical declaration type."""
    if typedef_map is None:
        typedef_map = {}
    ctype, base = classify_parameter(c_type_str, typedef_map)
    if ctype == CType.POINTER:
        return f"{base}*"
    if ctype == CType.ARRAY:
        return f"{base}[]"
    return base


def _is_float_type(c_type_str: str) -> bool:
    ctype, _ = classify_parameter(c_type_str)
    return ctype in (CType.FLOAT, CType.DOUBLE)


def _is_struct_type(c_type_str: str) -> bool:
    ctype, _ = classify_parameter(c_type_str)
    return ctype == CType.STRUCT


def _is_pointer_type(c_type_str: str) -> bool:
    ctype, _ = classify_parameter(c_type_str)
    return ctype == CType.POINTER


def _is_array_type(c_type_str: str) -> bool:
    ctype, _ = classify_parameter(c_type_str)
    return ctype == CType.ARRAY


def build_test_case_ir(
    tc: TestCase,
    func_meta: FunctionMeta,
    type_map: Dict,
    typedef_map: Dict[str, str] = None,
) -> Dict[str, Any]:
    """
    Build intermediate representation for a single test case.

    The IR contains all data the template needs to render the test function,
    with types resolved and declarations prepared.

    Args:
        tc: TestCase from schema
        func_meta: FunctionMeta for the function under test
        type_map: Type map from Stage 1B
        typedef_map: Typedef resolution map

    Returns:
        Dict with all template-ready data
    """
    if typedef_map is None:
        typedef_map = {}

    func_type_info = type_map.get("functions", {}).get(tc.function_name, {})
    params_info = func_type_info.get("params", {})

    param_declarations = []
    param_initializations = []
    call_arguments = []
    has_struct = False
    has_array = False
    has_pointer = False

    for param_name, param_value in tc.inputs.items():
        param_meta = params_info.get(param_name, {})
        c_type_str = param_meta.get("c_type", func_meta.return_type)

        if isinstance(param_value, dict):
            has_struct = True
            struct_type = c_type_str
            if _is_pointer_type(c_type_str):
                struct_type = c_type_str.replace("*", "").strip()
            param_declarations.append({"name": param_name, "ctype": struct_type})
            for fname, fval in param_value.items():
                param_initializations.append({
                    "name": param_name,
                    "is_struct": True,
                    "field_name": fname,
                    "field_value": fval,
                })
            call_arguments.append(param_name)
        elif _is_array_type(c_type_str):
            has_array = True
            base_type = c_type_str.replace("[]", "").replace("[0]", "").strip()
            param_declarations.append({"name": param_name, "ctype": f"{base_type}[]"})
            if isinstance(param_value, str) and param_value.startswith("{"):
                values_str = param_value.strip("{}")
            else:
                values_str = str(param_value)
            array_values = [v.strip() for v in values_str.split(",")]
            param_initializations.append({
                "name": param_name,
                "is_struct": False,
                "value": f"{{{', '.join(array_values)}}}",
                "is_array": True,
                "size_var": f"{param_name}_size",
                "size_val": f"{len(array_values)}u",
            })
            call_arguments.append(param_name)
            call_arguments.append(f"{param_name}_size")
        else:
            if _is_pointer_type(c_type_str):
                has_pointer = True
                resolved = _resolve_c_type(c_type_str, typedef_map)
                param_declarations.append({"name": param_name, "ctype": resolved})
            else:
                resolved = _resolve_c_type(c_type_str, typedef_map)
                param_declarations.append({"name": param_name, "ctype": resolved})
            param_initializations.append({
                "name": param_name,
                "is_struct": False,
                "value": str(param_value),
            })
            call_arguments.append(param_name)

    return_type = func_meta.return_type
    is_float_return = _is_float_type(return_type)
    is_void_return = return_type.strip() == "void"

    ir = {
        "scenario_id": tc.scenario_id,
        "function_name": tc.function_name,
        "scenario": tc.scenario,
        "test_type": tc.test_type.value,
        "intent": getattr(tc, "scenario", tc.scenario),
        "return_type": return_type,
        "inputs": tc.inputs,
        "expected_return": tc.expected_return,
        "expected_output_params": tc.expected_output_params,
        "stubs": {
            sname: {
                "return_value": sconfig.return_value,
                "expected_call_count": sconfig.expected_call_count,
                "output_params": sconfig.output_params,
            }
            for sname, sconfig in tc.stubs.items()
        },
        "param_declarations": param_declarations,
        "param_initializations": param_initializations,
        "call_arguments": call_arguments,
        "is_float_check": is_float_return and not is_void_return,
        "float_tolerance": "0.001f",
        "has_struct": has_struct,
        "has_array": has_array,
        "has_pointer": has_pointer,
        "needs_human_review": tc.needs_human_review,
        "human_review_reason": tc.human_review_reason,
    }
    return ir


def build_signatures_ir(tc_file: TestCaseFile, type_map: Dict) -> List[Dict]:
    """Build function signature list for extern declarations."""
    signatures = []
    for func_name, meta in tc_file.functions.items():
        func_type_info = type_map.get("functions", {}).get(func_name, {})
        params_info = func_type_info.get("params", {})

        param_strs = []
        for tc in tc_file.test_cases:
            if tc.function_name == func_name:
                for pname in tc.inputs:
                    pmeta = params_info.get(pname, {})
                    c_type = pmeta.get("c_type", "int")
                    resolved = _resolve_c_type(c_type)
                    param_strs.append(f"{resolved} {pname}")
                break

        if not param_strs:
            sig_params = meta.signature.split("(")
            if len(sig_params) > 1:
                param_strs = [sig_params[1].rstrip(")").strip()]
            else:
                param_strs = ["void"]

        signatures.append({
            "name": func_name,
            "return_type": meta.return_type,
            "params": param_strs if param_strs else ["void"],
            "is_static": False,
        })
    return signatures


def render_test_script(
    tc_file: TestCaseFile,
    type_map: Dict,
    typedef_map: Dict[str, str] = None,
) -> str:
    """
    Render the complete Cantata test script from TestCaseFile.

    Args:
        tc_file: Validated TestCaseFile
        type_map: Type map from Stage 1B
        typedef_map: Typedef resolution map

    Returns:
        Complete .c file content as string
    """
    if typedef_map is None:
        typedef_map = {}

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("cantata_test.c.j2")

    test_case_irs = []
    has_float_tests = False

    for func_name, meta in tc_file.functions.items():
        func_tests = [tc for tc in tc_file.test_cases if tc.function_name == func_name]
        for tc in func_tests:
            ir = build_test_case_ir(tc, meta, type_map, typedef_map)
            test_case_irs.append(ir)
            if ir["is_float_check"]:
                has_float_tests = True

    signatures = build_signatures_ir(tc_file, type_map)

    context = {
        "module_name": tc_file.module_name,
        "pr_number": tc_file.pr_number,
        "timestamp": tc_file.generated_at,
        "function_signatures": signatures,
        "hal_stubs": tc_file.hal_stubs,
        "has_float_tests": has_float_tests,
        "test_cases": test_case_irs,
    }

    return template.render(**context)


def render_header(tc_file: TestCaseFile, type_map: Dict) -> str:
    """
    Render the module header file from TestCaseFile.

    Args:
        tc_file: Validated TestCaseFile
        type_map: Type map from Stage 1B

    Returns:
        Complete .h file content as string
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        keep_trailing_newline=True,
    )
    template = env.get_template("cantata_header.h.j2")

    signatures = build_signatures_ir(tc_file, type_map)

    context = {
        "module_name": tc_file.module_name,
        "pr_number": tc_file.pr_number,
        "timestamp": tc_file.generated_at,
        "function_signatures": signatures,
    }

    return template.render(**context)


def write_stage2_outputs(
    tc_file: TestCaseFile,
    type_map: Dict,
    typedef_map: Dict[str, str] = None,
) -> Dict[str, str]:
    """
    Generate and write .c and .h files.

    Args:
        tc_file: Validated TestCaseFile
        type_map: Type map from Stage 1B
        typedef_map: Typedef resolution map

    Returns:
        Dict mapping file type to file path
    """
    if typedef_map is None:
        typedef_map = {}

    os.makedirs(GENERATED_TESTS_DIR, exist_ok=True)

    pr = tc_file.pr_number
    module = tc_file.module_name

    c_content = render_test_script(tc_file, type_map, typedef_map)
    h_content = render_header(tc_file, type_map)

    c_path = os.path.join(GENERATED_TESTS_DIR, f"test_{module}_{pr}.c")
    h_path = os.path.join(GENERATED_TESTS_DIR, f"{module}.h")

    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c_content)
    with open(h_path, "w", encoding="utf-8") as f:
        f.write(h_content)

    logger.info("Generated: %s", c_path)
    logger.info("Generated: %s", h_path)

    return {
        "test_script_c": c_path,
        "header_h": h_path,
    }


def run_stage2(
    json_path: str,
    type_map: Optional[Dict] = None,
    typedef_map: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Main entry point for Stage 2 — generate C code from testcases.json.

    Args:
        json_path: Path to testcases.json
        type_map: Optional type map (extracted from JSON if not provided)
        typedef_map: Optional typedef map

    Returns:
        Dict with generated file paths

    Raises:
        FileNotFoundError: If json_path doesn't exist
        ValueError: If schema validation fails
    """
    tc_file = load_testcase_file(json_path)

    if type_map is None:
        type_map = _extract_type_map_from_testcases(tc_file)

    if typedef_map is None:
        typedef_map = {}

    written = write_stage2_outputs(tc_file, type_map, typedef_map)

    return {
        **written,
        "test_cases_loaded": len(tc_file.test_cases),
        "functions_count": len(tc_file.functions),
    }


def _extract_type_map_from_testcases(tc_file: TestCaseFile) -> Dict:
    """
    Build a minimal type_map from TestCaseFile for standalone stage2 usage.

    When stage2 is run independently (e.g., after engineer edits JSON),
    we don't have the LLM-generated type_map. Build one from available data.
    """
    functions = {}
    for func_name, meta in tc_file.functions.items():
        params = {}
        func_tests = [tc for tc in tc_file.test_cases if tc.function_name == func_name]
        if func_tests:
            for pname, pval in func_tests[0].inputs.items():
                if isinstance(pval, dict):
                    params[pname] = {
                        "c_type": func_name,
                        "is_pointer": False,
                        "struct_fields": {k: "int" for k in pval.keys()},
                    }
                else:
                    params[pname] = {
                        "c_type": "int",
                        "is_pointer": pval == "NULL_PTR",
                    }
        functions[func_name] = {"return_type": meta.return_type, "params": params}
    return {"functions": functions}
