"""
Deterministic C literal suffix correction.

Runs between Stage 3A output and 3B input to fix value errors without
additional token cost: suffix fixes, NULL replacement, struct field cleanup.
"""

import json
import logging
import re
from typing import Any, Dict

from src.type_resolver import CType

logger = logging.getLogger(__name__)

_UNSIGNED_CTYPES = {
    CType.UINT8, CType.UINT16, CType.UINT32, CType.UINT64,
}
_FLOAT_CTYPES = {CType.FLOAT}


def _ctype_from_str(c_type_str: str) -> CType:
    """Map a c_type string from type_map to CType enum."""
    mapping = {
        "uint8_t": CType.UINT8, "uint8": CType.UINT8,
        "uint16_t": CType.UINT16, "uint16": CType.UINT16,
        "uint32_t": CType.UINT32, "uint32": CType.UINT32,
        "uint64_t": CType.UINT64, "uint64": CType.UINT64,
        "int8_t": CType.INT8, "int8": CType.INT8,
        "int16_t": CType.INT16, "int16": CType.INT16,
        "int32_t": CType.INT32, "int32": CType.INT32,
        "int64_t": CType.INT64, "int64": CType.INT64,
        "float": CType.FLOAT, "float32": CType.FLOAT, "float32_t": CType.FLOAT,
        "double": CType.DOUBLE, "float64": CType.DOUBLE, "float64_t": CType.DOUBLE,
        "bool": CType.BOOL, "_Bool": CType.BOOL, "boolean": CType.BOOL, "BOOL": CType.BOOL,
    }
    return mapping.get(c_type_str, CType.UNKNOWN)


def _is_unsigned(ctype: CType) -> bool:
    return ctype in _UNSIGNED_CTYPES


def _is_float(ctype: CType) -> bool:
    return ctype in _FLOAT_CTYPES


def _is_bool(ctype: CType) -> bool:
    return ctype == CType.BOOL


def _zero_value_for_ctype(ctype: CType) -> str:
    if _is_unsigned(ctype):
        return "0u"
    if _is_float(ctype):
        return "0.0f"
    if _is_bool(ctype):
        return "FALSE"
    return "0"


def _fix_value(value: str, ctype: CType) -> str:
    """Apply suffix and literal corrections to a single value string."""
    if not isinstance(value, str):
        return value

    if value == "NULL":
        logger.info("Replaced NULL with NULL_PTR")
        return "NULL_PTR"

    if _is_bool(ctype):
        if value == "false":
            logger.info("Replaced false with FALSE for BOOL")
            return "FALSE"
        if value == "true":
            logger.info("Replaced true with TRUE for BOOL")
            return "TRUE"

    if _is_unsigned(ctype) and re.match(r"^\d+$", value):
        logger.info("Added u suffix to unsigned value: %s -> %su", value, value)
        return value + "u"

    if _is_float(ctype) and re.match(r"^\d+\.\d+$", value):
        logger.info("Added f suffix to float value: %s -> %sf", value, value)
        return value + "f"

    return value


def _fix_expected_return(value: str) -> str:
    """Fix expected_return values."""
    if not isinstance(value, str):
        return value

    if value == "NULL":
        logger.info("Replaced NULL with NULL_PTR in expected_return")
        return "NULL_PTR"

    if value == "false":
        logger.info("Replaced false with FALSE in expected_return")
        return "FALSE"
    if value == "true":
        logger.info("Replaced true with TRUE in expected_return")
        return "TRUE"

    vague = {"depends", "varies", "unknown", "tbd"}
    if value.lower().strip() in vague:
        logger.warning("Replaced vague expected_return '%s' with E_NOT_OK", value)
        return "E_NOT_OK"

    return value


def _is_placeholder(value: str) -> bool:
    """Detect LLM-generated placeholder strings that aren't valid C values."""
    if not isinstance(value, str):
        return False
    placeholders = [
        r'_ptr$',              # ends with _ptr (e.g., existing_head_ptr, single_node_ptr)
        r'_list$',             # ends with _list
        r'^existing_',         # starts with existing_
        r'^freed_',            # starts with freed_
        r'^circular_',         # starts with circular_
        r'^dangling_',         # starts with dangling_
        r'^some_',             # starts with some_
        r'^valid_',            # starts with valid_
        r'^invalid_',          # starts with invalid_
        r'^dummy_',            # starts with dummy_
        r'^arbitrary_',        # starts with arbitrary_
    ]
    return any(re.search(p, value) for p in placeholders)


def sanitize_values(test_cases_json: Any, type_map: Dict) -> Any:
    """
    Fix C literal suffixes and values deterministically.

    Args:
        test_cases_json: Parsed JSON from Stage 3A (dict with 'test_cases' list)
        type_map: Parsed JSON from Stage 1B (dict with 'functions' key)

    Returns:
        Updated test_cases_json with corrected values
    """
    if isinstance(test_cases_json, str):
        test_cases_json = json.loads(test_cases_json)

    type_funcs = type_map.get("functions", {}) if isinstance(type_map, dict) else {}

    for tc in test_cases_json.get("test_cases", []):
        fn_name = tc.get("function_name", "")
        func_type_info = type_funcs.get(fn_name, {})
        params_info = func_type_info.get("params", {})

        inputs = tc.get("inputs", {})
        for param_name, param_value in inputs.items():
            param_meta = params_info.get(param_name, {})
            c_type_str = param_meta.get("c_type", "")
            ctype = _ctype_from_str(c_type_str)
            struct_fields = param_meta.get("struct_fields", {})

            if isinstance(param_value, dict) and struct_fields:
                allowed_fields = set(struct_fields.keys())

                keys_to_remove = [k for k in param_value if k not in allowed_fields]
                for k in keys_to_remove:
                    logger.warning(
                        "Removed unknown struct field '%s' from %s.%s", k, fn_name, param_name
                    )
                    del param_value[k]

                for field_name, field_c_type in struct_fields.items():
                    if field_name not in param_value:
                        field_ctype = _ctype_from_str(field_c_type)
                        zero_val = _zero_value_for_ctype(field_ctype)
                        param_value[field_name] = zero_val
                        logger.info(
                            "Added missing struct field '%s' with zero value '%s' to %s.%s",
                            field_name, zero_val, fn_name, param_name,
                        )
                    else:
                        field_ctype = _ctype_from_str(field_c_type)
                        param_value[field_name] = _fix_value(param_value[field_name], field_ctype)

            elif isinstance(param_value, str):
                inputs[param_name] = _fix_value(param_value, ctype)

        if "expected_return" in tc:
            tc["expected_return"] = _fix_expected_return(tc["expected_return"])

        for pname, pval in tc.get("expected_output_params", {}).items():
            if isinstance(pval, str):
                tc["expected_output_params"][pname] = _fix_expected_return(pval)

    return test_cases_json
