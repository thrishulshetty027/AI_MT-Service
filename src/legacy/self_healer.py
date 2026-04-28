import os
import re


def fix_array_scalar_init(c_code: str) -> tuple[str, list[str]]:
    fixes = []
    pattern = re.compile(r"(int|float|double|char)\s+(\w+)\[\]\s*=\s*(\d+)\s*;")

    def _replacer(m):
        type_name = m.group(1)
        var_name = m.group(2)
        fixes.append(f"Array '{var_name}' initialized to scalar {m.group(3)} (cannot auto-fix without data)")
        return m.group(0)

    return pattern.sub(_replacer, c_code), fixes


def fix_brackets_in_calls(c_code: str) -> tuple[str, list[str]]:
    fixes = []
    lines = c_code.split("\n")
    fixed_lines = []
    for line in lines:
        if line.strip().startswith("extern "):
            fixed_lines.append(line)
            continue
        if re.match(r"^\s*(int|float|double|char|long|short|unsigned)\s+\w+\[\]", line):
            fixed_lines.append(line)
            continue
        original = line
        fixed = re.sub(r"(\w+)\[\]", r"\1", line)
        if fixed != original:
            bracket_matches = re.findall(r"(\w+)\[\]", original)
            for bm in bracket_matches:
                fixes.append(f"Removed brackets from '{bm}[]' in function call")
        fixed_lines.append(fixed)
    return "\n".join(fixed_lines), fixes


def fix_missing_semicolons(c_code: str) -> tuple[str, list[str]]:
    fixes = []
    lines = c_code.split("\n")
    fixed_lines = []
    for line in lines:
        stripped = line.rstrip()
        if re.match(r"^\s*(int|float|double|char|long|short|unsigned)\s+\w+(\[\])?\s*=\s*.+$", stripped):
            if not stripped.endswith(";"):
                fixed_lines.append(stripped + ";")
                fixes.append("Added missing semicolon to variable declaration")
                continue
        fixed_lines.append(line)
    return "\n".join(fixed_lines), fixes


def fix_void_return_assignment(c_code: str) -> tuple[str, list[str]]:
    fixes = []
    pattern = re.compile(r"(int|float|double|char|long)\s+result\s*=\s*(\w+)\s*\(([^)]*)\)\s*;")
    known_void: set[str] = set()
    for m in re.finditer(r"extern\s+void\s+(\w+)\s*\(", c_code):
        known_void.add(m.group(1))

    def _replacer(m):
        func_name = m.group(2)
        if func_name in known_void:
            fixes.append(f"Removed result assignment from void function '{func_name}'")
            return f"{func_name}({m.group(3)});"
        return m.group(0)

    return pattern.sub(_replacer, c_code), fixes


def heal_c_code(c_code: str) -> tuple[str, list[str]]:
    all_fixes: list[str] = []

    code, fixes = fix_brackets_in_calls(c_code)
    all_fixes.extend(fixes)

    code, fixes = fix_void_return_assignment(code)
    all_fixes.extend(fixes)

    code, fixes = fix_missing_semicolons(code)
    all_fixes.extend(fixes)

    code, fixes = fix_array_scalar_init(code)
    all_fixes.extend(fixes)

    return code, all_fixes
