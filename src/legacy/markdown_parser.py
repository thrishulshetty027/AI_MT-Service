import re
from src.ir_models import TestCase

_C_TYPE_KEYWORDS = (
    "char", "int", "float", "double", "long", "short",
    "unsigned", "signed", "void", "struct",
)


def _is_c_declaration_format(input_str: str) -> bool:
    if ";" not in input_str:
        return False
    for kw in _C_TYPE_KEYWORDS:
        if re.search(rf'\b{kw}\b', input_str):
            return True
    return False


def _split_on_semicolons(s: str) -> list[str]:
    parts = []
    current = ""
    in_string = False
    in_braces = 0

    for ch in s:
        if ch == '"' and in_braces == 0:
            in_string = not in_string
            current += ch
        elif ch == '{' and not in_string:
            in_braces += 1
            current += ch
        elif ch == '}' and not in_string:
            in_braces -= 1
            current += ch
        elif ch == ';' and not in_string and in_braces == 0:
            parts.append(current)
            current = ""
        else:
            current += ch

    if current.strip():
        parts.append(current)

    return parts


def _parse_c_declarations(input_str: str) -> tuple[dict[str, str], dict[str, str]]:
    values = {}
    declarations = {}

    parts = _split_on_semicolons(input_str)

    for part in parts:
        part = part.strip()
        if not part or "=" not in part:
            continue

        eq_pos = part.index("=")
        before_eq = part[:eq_pos].rstrip()
        value = part[eq_pos + 1:].strip()

        name_match = re.search(r'(\w+)\s*(?:\[[^\]]*\])?\s*$', before_eq)
        if name_match:
            name = name_match.group(1)
            values[name] = value
            declarations[name] = part

    return values, declarations


def parse_input_values(input_str: str) -> tuple[dict[str, str], dict[str, str]]:
    if not input_str or not input_str.strip():
        return {}, {}

    if _is_c_declaration_format(input_str):
        return _parse_c_declarations(input_str)

    values = {}
    depth = 0
    current_key = ""
    current_value = ""
    in_key = True

    i = 0
    while i < len(input_str):
        ch = input_str[i]

        if ch == "{" and in_key:
            depth += 1
            current_value += ch
            in_key = False
        elif ch == "{" and not in_key:
            depth += 1
            current_value += ch
        elif ch == "}":
            depth -= 1
            current_value += ch
            if depth == 0 and current_key:
                values[current_key.strip()] = current_value.strip()
                current_key = ""
                current_value = ""
                in_key = True
        elif ch == "=" and in_key and depth == 0:
            current_key = current_value
            current_value = ""
            in_key = False
        elif ch == "," and depth == 0:
            if current_key:
                values[current_key.strip()] = current_value.strip()
            current_key = ""
            current_value = ""
            in_key = True
        else:
            current_value += ch

        i += 1

    if current_key and current_value:
        values[current_key.strip()] = current_value.strip()

    return values, {}


def parse_test_cases(markdown_content: str) -> list[TestCase]:
    if not markdown_content or not markdown_content.strip():
        return []

    lines = markdown_content.split("\n")
    test_cases = []
    headers = []
    in_table = False

    column_map = {
        "test case id": "test_id",
        "test case": "test_id",
        "function name": "function_name",
        "test scenario": "scenario",
        "input values": "input_values",
        "expected result": "expected_result",
        "test type": "test_type",
    }

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if "|" in stripped and not in_table:
            header_candidates = [h.strip().lower() for h in stripped.split("|")[1:-1]]
            if any(key in " ".join(header_candidates) for key in ["test case", "function name", "test scenario"]):
                headers = [h.strip().lower() for h in stripped.split("|")[1:-1]]
                in_table = True
                continue

        if not in_table:
            continue

        if stripped.startswith("|") and re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue

        if not stripped.startswith("|"):
            continue

        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) != len(headers):
            continue

        row = dict(zip(headers, cells))

        field_map = {}
        for col_header, value in row.items():
            mapped = column_map.get(col_header, None)
            if mapped:
                field_map[mapped] = value

        if not field_map.get("function_name", "").strip():
            continue

        input_values, declarations = parse_input_values(field_map.get("input_values", ""))

        try:
            tc = TestCase(
                test_id=field_map.get("test_id", ""),
                function_name=field_map.get("function_name", ""),
                scenario=field_map.get("scenario", ""),
                input_values=input_values,
                expected_result=field_map.get("expected_result", ""),
                test_type=field_map.get("test_type", "normal"),
                declarations=declarations,
            )
            test_cases.append(tc)
        except Exception:
            continue

    return test_cases
