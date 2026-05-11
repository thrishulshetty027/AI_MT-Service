"""
MSVC17 compile validator with self-healing error-to-IR fix mapping.

Compiles generated .c files with cl.exe /Za, parses error codes,
maps them to IR fixes, regenerates from templates, and retries up to 3 times.
"""

import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_COMPILE_ATTEMPTS = 3

ERROR_FIX_MAP = {
    "C2039": "wrong_struct_field",
    "C2065": "undeclared_identifier",
    "C2143": "declaration_after_statement",
    "C4013": "undefined_function",
    "C2440": "type_mismatch",
    "C2106": "const_assignment",
}


def parse_msvc_errors(compile_output: str) -> List[Dict[str, str]]:
    """
    Parse MSVC error output into structured error records.

    Args:
        compile_output: Raw stderr from cl.exe

    Returns:
        List of dicts with keys: error_code, file, line, message
    """
    errors = []
    pattern = re.compile(
        r"(?P<file>[^\s]+)\((?P<line>\d+)\)\s*:\s*(?:error|warning)\s*(?P<code>C\d+):\s*(?P<msg>.+)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(compile_output):
        errors.append({
            "error_code": match.group("code"),
            "file": match.group("file"),
            "line": match.group("line"),
            "message": match.group("msg").strip(),
        })
    return errors


def fix_ir_for_error(
    error: Dict[str, str],
    type_map: Dict,
    test_case_irs: List[Dict],
) -> Optional[Dict[str, Any]]:
    """
    Map a compile error to an IR fix.

    Args:
        error: Parsed error dict
        type_map: Type map from Stage 1B
        test_case_irs: Current test case IRs

    Returns:
        Fix dict with: error_code, fix_type, description, or None if unfixable
    """
    code = error.get("error_code", "")
    msg = error.get("message", "")
    fix_type = ERROR_FIX_MAP.get(code)

    if not fix_type:
        return None

    if fix_type == "wrong_struct_field":
        field_match = re.search(r"'(\w+)'", msg)
        struct_match = re.search(r"'(\w+)'", msg[field_match.end():] if field_match else msg)
        if field_match:
            field_name = field_match.group(1)
            return {
                "error_code": code,
                "fix_type": fix_type,
                "field_name": field_name,
                "description": f"Remove struct field '{field_name}' not in type_map",
            }

    elif fix_type == "undeclared_identifier":
        id_match = re.search(r"'(\w+)'", msg)
        if id_match:
            ident = id_match.group(1)
            return {
                "error_code": code,
                "fix_type": fix_type,
                "identifier": ident,
                "description": f"Add extern declaration for '{ident}'",
            }

    elif fix_type == "undefined_function":
        func_match = re.search(r"'(\w+)'", msg)
        if func_match:
            func_name = func_match.group(1)
            return {
                "error_code": code,
                "fix_type": fix_type,
                "function_name": func_name,
                "description": f"Add extern for undefined function '{func_name}'",
            }

    elif fix_type == "type_mismatch":
        return {
            "error_code": code,
            "fix_type": fix_type,
            "description": f"Type mismatch: {msg}",
        }

    elif fix_type == "declaration_after_statement":
        return {
            "error_code": code,
            "fix_type": fix_type,
            "description": "TEMPLATE BUG: declaration after statement — escalate",
        }

    elif fix_type == "const_assignment":
        return {
            "error_code": code,
            "fix_type": fix_type,
            "description": f"Cannot assign to const: {msg}",
        }

    return None


def apply_ir_fixes(
    fixes: List[Dict],
    type_map: Dict,
    test_case_irs: List[Dict],
    signatures: List[Dict],
) -> Tuple[Dict, List[Dict], List[Dict]]:
    """
    Apply IR fixes to type_map, test cases, and signatures.

    Returns:
        Tuple of (updated_type_map, updated_test_case_irs, updated_signatures)
    """
    import copy
    updated_type_map = copy.deepcopy(type_map)
    updated_irs = copy.deepcopy(test_case_irs)
    updated_sigs = copy.deepcopy(signatures)

    for fix in fixes:
        fix_type = fix.get("fix_type")

        if fix_type == "wrong_struct_field":
            field_name = fix.get("field_name")
            for ir in updated_irs:
                for pname, pval in ir.get("inputs", {}).items():
                    if isinstance(pval, dict) and field_name in pval:
                        del pval[field_name]
                        logger.info("Removed field '%s' from %s", field_name, pname)
                for init in ir.get("param_initializations", []):
                    if init.get("is_struct") and init.get("field_name") == field_name:
                        ir["param_initializations"].remove(init)

        elif fix_type in ("undeclared_identifier", "undefined_function"):
            func_name = fix.get("function_name") or fix.get("identifier")
            if func_name:
                already_exists = any(s["name"] == func_name for s in updated_sigs)
                if not already_exists:
                    updated_sigs.append({
                        "name": func_name,
                        "return_type": "int",
                        "params": ["void"],
                        "is_static": False,
                    })
                    logger.info("Added extern for '%s'", func_name)

        elif fix_type == "declaration_after_statement":
            logger.error("C2143: Template bug detected — cannot auto-fix. Escalating.")
            break

    return updated_type_map, updated_irs, updated_sigs


def compile_with_msvc(
    c_file_path: str,
    include_dirs: List[str] = None,
    cl_exe: str = "cl.exe",
) -> Dict[str, Any]:
    """
    Compile a .c file with MSVC17 cl.exe /Za.

    Args:
        c_file_path: Path to the .c file
        include_dirs: Additional include directories
        cl_exe: Path to cl.exe

    Returns:
        Dict with: success, output, errors, attempt
    """
    if include_dirs is None:
        include_dirs = []

    cmd = [cl_exe, "/Za", "/nologo", "/W3", "/c"]
    for inc_dir in include_dirs:
        cmd.extend(["/I", inc_dir])
    cmd.append(c_file_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        errors = parse_msvc_errors(result.stderr + result.stdout)
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "errors": errors,
        }
    except FileNotFoundError:
        logger.warning("cl.exe not found — skipping actual compilation")
        return {
            "success": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "errors": [],
            "skipped": True,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Compilation timed out (60s)",
            "errors": [],
        }


def run_compile_loop(
    c_file_path: str,
    tc_file_path: str,
    type_map: Dict,
    include_dirs: List[str] = None,
    cl_exe: str = "cl.exe",
    regenerate_fn=None,
) -> Dict[str, Any]:
    """
    Compile with self-healing retry loop.

    Attempts compilation up to MAX_COMPILE_ATTEMPTS times.
    On failure, parses errors, maps to IR fixes, regenerates, retries.

    Args:
        c_file_path: Path to generated .c file
        tc_file_path: Path to testcases.json
        type_map: Type map from Stage 1B
        include_dirs: Additional include directories
        cl_exe: Path to cl.exe
        regenerate_fn: Function to regenerate .c from IR (called with fixes applied)

    Returns:
        Dict with: success, attempts, errors_fixed, compile_report
    """
    all_errors_fixed = []
    attempt = 0
    current_type_map = type_map
    current_errors = []

    for attempt in range(1, MAX_COMPILE_ATTEMPTS + 1):
        logger.info("Compile attempt %d/%d: %s", attempt, MAX_COMPILE_ATTEMPTS, c_file_path)

        result = compile_with_msvc(c_file_path, include_dirs, cl_exe)
        if result.get("skipped"):
            logger.info("Compilation skipped (cl.exe not available)")
            return {
                "success": False,
                "attempts": attempt,
                "errors_fixed": [],
                "skipped": True,
                "compile_report": {"attempts": attempt, "skipped": True},
            }

        if result["success"]:
            logger.info("Compilation succeeded on attempt %d", attempt)
            return {
                "success": True,
                "attempts": attempt,
                "errors_fixed": all_errors_fixed,
                "compile_report": {
                    "attempts": attempt,
                    "errors_fixed": [f["description"] for f in all_errors_fixed],
                    "final_errors": [],
                },
            }

        parsed_errors = result.get("errors", [])
        logger.warning("Compile attempt %d failed with %d errors", attempt, len(parsed_errors))

        fixes = []
        for error in parsed_errors:
            fix = fix_ir_for_error(error, current_type_map, [])
            if fix:
                fixes.append(fix)

        has_template_bug = any(f.get("fix_type") == "declaration_after_statement" for f in fixes)
        if has_template_bug:
            logger.error("C2143 template bug — cannot auto-fix. Escalating.")
            return {
                "success": False,
                "attempts": attempt,
                "errors_fixed": all_errors_fixed,
                "compile_report": {
                    "attempts": attempt,
                    "errors_fixed": [f["description"] for f in all_errors_fixed],
                    "final_errors": [e["message"] for e in parsed_errors],
                    "escalated": True,
                    "escalation_reason": "C2143 declaration after statement — template bug",
                },
            }

        if fixes and regenerate_fn:
            all_errors_fixed.extend(fixes)
            logger.info("Applying %d fixes and regenerating", len(fixes))
            regenerate_fn(fixes)
        elif attempt < MAX_COMPILE_ATTEMPTS:
            logger.warning("No fixes applicable — retrying without changes")
        else:
            break

    return {
        "success": False,
        "attempts": attempt,
        "errors_fixed": all_errors_fixed,
        "compile_report": {
            "attempts": attempt,
            "errors_fixed": [f["description"] for f in all_errors_fixed],
            "final_errors": [e.get("message", "") for e in current_errors],
            "escalated": True,
            "escalation_reason": f"Failed after {attempt} attempts",
        },
    }


GENERATED_TESTS_DIR = "generated_tests"


def write_compile_report(
    pr_number: str,
    compile_result: Dict[str, Any],
    output_dir: str = None,
) -> str:
    """
    Write compile report JSON.

    Args:
        pr_number: PR identifier
        compile_result: Result from run_compile_loop
        output_dir: Output directory

    Returns:
        Path to written compile report
    """
    if output_dir is None:
        output_dir = GENERATED_TESTS_DIR
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"compile_report_{pr_number}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(compile_result.get("compile_report", {}), f, indent=2)
    return report_path
