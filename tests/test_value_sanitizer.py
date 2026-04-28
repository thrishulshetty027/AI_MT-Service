"""Tests for value_sanitizer.py — deterministic C literal suffix correction."""

import json
import pytest

from src.value_sanitizer import sanitize_values


def _make_type_map(func_name="test_func", params=None):
    if params is None:
        params = {}
    return {"functions": {func_name: {"params": params}}}


def _make_test_cases(cases):
    return {"test_cases": cases}


def test_sanitize_adds_u_suffix_uint():
    type_map = _make_type_map("f", {
        "a": {"c_type": "uint16_t", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"a": "255"}, "expected_return": "0u",
    }])
    result = sanitize_values(tc, type_map)
    assert result["test_cases"][0]["inputs"]["a"] == "255u"


def test_sanitize_adds_f_suffix_float():
    type_map = _make_type_map("f", {
        "x": {"c_type": "float", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"x": "3.14"}, "expected_return": "0.0f",
    }])
    result = sanitize_values(tc, type_map)
    assert result["test_cases"][0]["inputs"]["x"] == "3.14f"


def test_sanitize_replaces_NULL_with_NULL_PTR():
    type_map = _make_type_map("f", {
        "ptr": {"c_type": "uint8_t*", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"ptr": "NULL"}, "expected_return": "E_NOT_OK",
    }])
    result = sanitize_values(tc, type_map)
    assert result["test_cases"][0]["inputs"]["ptr"] == "NULL_PTR"


def test_sanitize_replaces_false_true_with_FALSE_TRUE():
    type_map = _make_type_map("f", {
        "flag": {"c_type": "BOOL", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"flag": "true"}, "expected_return": "E_OK",
    }])
    result = sanitize_values(tc, type_map)
    assert result["test_cases"][0]["inputs"]["flag"] == "TRUE"


def test_sanitize_strips_unknown_struct_fields():
    type_map = _make_type_map("f", {
        "act": {"c_type": "Actuator_t", "struct_fields": {"field_a": "uint8_t", "field_b": "BOOL"}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"act": {"field_a": "10u", "field_b": "TRUE", "bogus_field": "99"}},
        "expected_return": "E_OK",
    }])
    result = sanitize_values(tc, type_map)
    assert "bogus_field" not in result["test_cases"][0]["inputs"]["act"]


def test_sanitize_adds_missing_struct_fields():
    type_map = _make_type_map("f", {
        "act": {"c_type": "Actuator_t", "struct_fields": {"field_a": "uint8_t", "field_b": "BOOL"}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"act": {"field_a": "10u"}},
        "expected_return": "E_OK",
    }])
    result = sanitize_values(tc, type_map)
    assert "field_b" in result["test_cases"][0]["inputs"]["act"]
    assert result["test_cases"][0]["inputs"]["act"]["field_b"] == "FALSE"


def test_sanitize_rejects_vague_expected_return():
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {}, "expected_return": "depends",
    }])
    result = sanitize_values(tc, {"functions": {"f": {"params": {}}}})
    assert result["test_cases"][0]["expected_return"] == "E_NOT_OK"


def test_sanitize_no_change_on_correct_values():
    type_map = _make_type_map("f", {
        "a": {"c_type": "uint16_t", "struct_fields": {}},
        "b": {"c_type": "float", "struct_fields": {}},
        "c": {"c_type": "uint8_t*", "struct_fields": {}},
        "d": {"c_type": "BOOL", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"a": "255u", "b": "3.14f", "c": "NULL_PTR", "d": "TRUE"},
        "expected_return": "E_OK",
    }])
    result = sanitize_values(tc, type_map)
    inp = result["test_cases"][0]["inputs"]
    assert inp["a"] == "255u"
    assert inp["b"] == "3.14f"
    assert inp["c"] == "NULL_PTR"
    assert inp["d"] == "TRUE"


def test_sanitize_handles_string_input():
    type_map = _make_type_map("f", {"a": {"c_type": "uint16_t", "struct_fields": {}}})
    tc_str = json.dumps({"test_cases": [{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"a": "10"}, "expected_return": "E_OK",
    }]})
    result = sanitize_values(tc_str, type_map)
    assert isinstance(result, dict)
    assert result["test_cases"][0]["inputs"]["a"] == "10u"


def test_sanitize_mixed_test_cases():
    type_map = _make_type_map("f", {
        "val": {"c_type": "uint32_t", "struct_fields": {}},
        "fl": {"c_type": "float", "struct_fields": {}},
        "ptr": {"c_type": "uint8_t*", "struct_fields": {}},
        "en": {"c_type": "BOOL", "struct_fields": {}},
    })
    tc = _make_test_cases([
        {
            "scenario_id": "S001", "function_name": "f",
            "inputs": {"val": "100", "fl": "1.5", "ptr": "NULL", "en": "false"},
            "expected_return": "E_OK",
        },
        {
            "scenario_id": "S002", "function_name": "f",
            "inputs": {"val": "0u", "fl": "0.0f", "ptr": "NULL_PTR", "en": "TRUE"},
            "expected_return": "depends",
        },
    ])
    result = sanitize_values(tc, type_map)
    r0 = result["test_cases"][0]
    assert r0["inputs"]["val"] == "100u"
    assert r0["inputs"]["fl"] == "1.5f"
    assert r0["inputs"]["ptr"] == "NULL_PTR"
    assert r0["inputs"]["en"] == "FALSE"
    r1 = result["test_cases"][1]
    assert r1["expected_return"] == "E_NOT_OK"


def test_sanitize_expected_output_params():
    type_map = _make_type_map("f", {
        "out": {"c_type": "uint8_t*", "struct_fields": {}},
    })
    tc = _make_test_cases([{
        "scenario_id": "S001", "function_name": "f",
        "inputs": {"out": "NULL_PTR"},
        "expected_return": "E_OK",
        "expected_output_params": {"result_val": "NULL"},
    }])
    result = sanitize_values(tc, type_map)
    assert result["test_cases"][0]["expected_output_params"]["result_val"] == "NULL_PTR"
