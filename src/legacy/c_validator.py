import re


def validate_c_code(c_code: str) -> list[str]:
    if not c_code or not c_code.strip():
        return ["Empty C code"]

    errors = []

    if re.search(r"\w+\[\]\s*=\s*[0-9]+\s*;", c_code):
        errors.append("Array initialized to scalar (e.g. arr[] = 0) — data loss")

    non_extern_code = "\n".join(
        line for line in c_code.split("\n")
        if not line.strip().startswith("extern ")
    )
    for m in re.finditer(r"(\w+)\(\s*([^)]*)\)", non_extern_code):
        args_str = m.group(2)
        if re.search(r"\w+\[\]", args_str):
            errors.append("Array brackets in function call argument")
            break

    if re.search(r"function_under_test", c_code):
        errors.append("Placeholder 'function_under_test' found in output")

    if c_code.lstrip().startswith("# ") or c_code.lstrip().startswith("Generated at:"):
        errors.append("Markdown preamble in C file")

    if not re.search(r"\bmain\s*\(", c_code):
        errors.append("Missing main() function")

    if not re.search(r"#include\s*<cantpp\.h>", c_code):
        errors.append("Missing #include <cantpp.h>")

    if not re.search(r"#define\s+TEST_SCRIPT_GENERATOR", c_code):
        errors.append("Missing #define TEST_SCRIPT_GENERATOR")

    if not re.search(r"rule_set\s*\(", c_code):
        errors.append("Missing rule_set() coverage function")

    if not re.search(r"ANALYSIS_CHECK\s*\(", c_code):
        errors.append("Missing ANALYSIS_CHECK coverage calls")

    if not re.search(r"OPEN_LOG\s*\(", c_code):
        errors.append("Missing OPEN_LOG() call")

    if not re.search(r"START_SCRIPT\s*\(", c_code):
        errors.append("Missing START_SCRIPT() call")

    if not re.search(r"END_SCRIPT\s*\(", c_code):
        errors.append("Missing END_SCRIPT() call")

    if not re.search(r"static\s+void\s+initialise_global_data\s*\(", c_code):
        errors.append("Missing static initialise_global_data()")

    if not re.search(r"EXPORT_COVERAGE\s*\(", c_code):
        errors.append("Missing EXPORT_COVERAGE() call")

    if re.search(r"\bint\s+\w+\s*=\s*[^;{]*$", c_code, re.MULTILINE):
        pass

    extern_block = ""
    in_extern = False
    for line in c_code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("extern "):
            in_extern = True
        if in_extern:
            if stripped and not stripped.startswith("extern ") and not stripped.startswith("/*") and not stripped.startswith("*"):
                in_extern = False
            else:
                extern_block += stripped + "\n"

    if "{" in extern_block:
        errors.append("Curly brace in extern declaration section")

    return errors


def validate_array_values(c_code: str, expected_arrays: dict[str, str]) -> list[str]:
    errors = []
    for var_name, expected_init in expected_arrays.items():
        pattern = rf"{re.escape(var_name)}\[\]\s*=\s*({{[^}}]*}})"
        m = re.search(pattern, c_code)
        if not m:
            errors.append(f"Array '{var_name}' not found or not brace-initialized")
            continue
        actual = m.group(1)
        expected = expected_init.strip()
        if actual.replace(" ", "") != expected.replace(" ", ""):
            errors.append(
                f"Array '{var_name}' mismatch: expected {expected}, got {actual}"
            )
    return errors
