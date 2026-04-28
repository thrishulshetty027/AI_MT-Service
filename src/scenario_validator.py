"""
Deterministic scenario gap detection and auto-fill.

Runs between Stage 2A output and 2B input to catch missing null_ptr,
boundary, and normal scenarios without additional token cost.
"""

import json
import logging
import re
from typing import Any, Dict, List

from src.schemas import TestType

logger = logging.getLogger(__name__)


def fill_gaps(
    scenarios_json: Any,
    type_map: Dict,
    function_signatures: List[Dict],
) -> Any:
    """
    Add missing null_ptr, boundary, and normal scenarios deterministically.

    Args:
        scenarios_json: Parsed JSON from Stage 2A (dict with 'scenarios' list)
        type_map: Parsed JSON from Stage 1B (dict with 'functions' key)
        function_signatures: List of function signature dicts from context assembler

    Returns:
        Updated scenarios_json with gap-fill scenarios added
    """
    if isinstance(scenarios_json, str):
        scenarios_json = json.loads(scenarios_json)

    scenarios = scenarios_json.get("scenarios", [])

    func_coverage: Dict[str, set] = {}
    for sc in scenarios:
        fn = sc.get("function_name", "")
        if fn not in func_coverage:
            func_coverage[fn] = set()
        tt = sc.get("test_type", "")
        func_coverage[fn].add(tt.upper())

    max_gap_num = 0
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        m = re.match(r"S_GAP_(\d+)", sid)
        if m:
            max_gap_num = max(max_gap_num, int(m.group(1)))

    type_funcs = type_map.get("functions", {}) if isinstance(type_map, dict) else {}

    for sig in function_signatures:
        fn_name = sig.get("name", "")
        if not fn_name:
            continue

        covered = func_coverage.get(fn_name, set())

        if "NORMAL" not in covered:
            max_gap_num += 1
            gap_sc = {
                "function_name": fn_name,
                "scenario_id": f"S_GAP_{max_gap_num:03d}",
                "scenario_name": "Normal operation",
                "test_type": "NORMAL",
                "intent": f"Verify normal operation of {fn_name} with valid inputs",
                "branch_targeted": None,
                "expected_behavior": "Returns expected value for valid inputs",
            }
            scenarios.append(gap_sc)
            covered.add("NORMAL")
            func_coverage[fn_name] = covered
            logger.info("Gap filled: added NORMAL scenario for %s (S_GAP_%03d)", fn_name, max_gap_num)

        func_type_info = type_funcs.get(fn_name, {})
        params = func_type_info.get("params", {})

        for param_name, param_info in params.items():
            is_pointer = param_info.get("is_pointer", False)
            c_type = param_info.get("c_type", "").lower()

            is_numeric = any(
                kw in c_type
                for kw in ["uint", "int", "float", "double", "int8", "int16", "int32", "int64"]
            )

            if is_pointer and "NULL_PTR" not in covered:
                max_gap_num += 1
                gap_sc = {
                    "function_name": fn_name,
                    "scenario_id": f"S_GAP_{max_gap_num:03d}",
                    "scenario_name": f"NULL pointer test for {param_name}",
                    "test_type": "NULL_PTR",
                    "intent": f"Verify NULL_PTR handling for {param_name}",
                    "branch_targeted": f"{param_name} == NULL_PTR",
                    "expected_behavior": "Returns error code or handles gracefully",
                }
                scenarios.append(gap_sc)
                covered.add("NULL_PTR")
                func_coverage[fn_name] = covered
                logger.info("Gap filled: added NULL_PTR scenario for %s.%s (S_GAP_%03d)", fn_name, param_name, max_gap_num)

            if is_numeric:
                if "BOUNDARY_MIN" not in covered:
                    max_gap_num += 1
                    gap_sc = {
                        "function_name": fn_name,
                        "scenario_id": f"S_GAP_{max_gap_num:03d}",
                        "scenario_name": f"Boundary minimum for {param_name}",
                        "test_type": "BOUNDARY_MIN",
                        "intent": f"Verify behavior when {param_name} is at minimum value",
                        "branch_targeted": None,
                        "expected_behavior": "Handles minimum boundary correctly",
                    }
                    scenarios.append(gap_sc)
                    covered.add("BOUNDARY_MIN")
                    func_coverage[fn_name] = covered
                    logger.info("Gap filled: added BOUNDARY_MIN scenario for %s.%s (S_GAP_%03d)", fn_name, param_name, max_gap_num)

                if "BOUNDARY_MAX" not in covered:
                    max_gap_num += 1
                    gap_sc = {
                        "function_name": fn_name,
                        "scenario_id": f"S_GAP_{max_gap_num:03d}",
                        "scenario_name": f"Boundary maximum for {param_name}",
                        "test_type": "BOUNDARY_MAX",
                        "intent": f"Verify behavior when {param_name} is at maximum value",
                        "branch_targeted": None,
                        "expected_behavior": "Handles maximum boundary correctly",
                    }
                    scenarios.append(gap_sc)
                    covered.add("BOUNDARY_MAX")
                    func_coverage[fn_name] = covered
                    logger.info("Gap filled: added BOUNDARY_MAX scenario for %s.%s (S_GAP_%03d)", fn_name, param_name, max_gap_num)

    scenarios_json["scenarios"] = scenarios
    return scenarios_json


def validate_scenarios(scenarios_json: Any) -> List[str]:
    """
    Validate scenario list for structural correctness.

    Args:
        scenarios_json: Parsed or string JSON with 'scenarios' list

    Returns:
        List of error strings (empty = valid)
    """
    if isinstance(scenarios_json, str):
        scenarios_json = json.loads(scenarios_json)

    scenarios = scenarios_json.get("scenarios", [])
    errors: List[str] = []
    valid_test_types = {t.value for t in TestType}
    seen_ids: Dict[str, int] = {}
    required_fields = ["function_name", "scenario_id", "test_type", "intent"]

    for i, sc in enumerate(scenarios):
        for rf in required_fields:
            if rf not in sc or not sc[rf]:
                errors.append(f"Scenario {i}: missing required field '{rf}'")

        tt = sc.get("test_type", "")
        if tt and tt.upper() not in valid_test_types:
            errors.append(f"Scenario {i}: invalid test_type '{tt}'")

        sid = sc.get("scenario_id", "")
        if sid:
            if sid in seen_ids:
                errors.append(
                    f"Scenario {i}: duplicate scenario_id '{sid}' "
                    f"(first seen at scenario {seen_ids[sid]})"
                )
            else:
                seen_ids[sid] = i

    return errors
