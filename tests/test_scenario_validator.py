"""Tests for scenario_validator.py — deterministic gap filler and validator."""

import json
import pytest

from src.scenario_validator import fill_gaps, validate_scenarios


def _make_type_map(func_name="process_data", params=None):
    if params is None:
        params = {
            "data_ptr": {
                "c_type": "uint8_t*",
                "is_pointer": True,
                "is_const": False,
                "is_array": False,
                "struct_name": None,
                "struct_fields": {},
                "valid_min": "0u",
                "valid_max": "255u",
            }
        }
    return {
        "functions": {
            func_name: {
                "return_type": "uint8_t",
                "return_meaning": "result",
                "return_valid_values": ["0u", "255u"],
                "params": params,
            }
        }
    }


def _make_signatures(func_name="process_data", param_list=None):
    if param_list is None:
        param_list = [{"name": "data_ptr", "type": "uint8_t*"}]
    return [{"name": func_name, "params": param_list}]


def _make_scenarios(scenarios):
    return {"scenarios": scenarios}


def test_fill_gaps_adds_null_ptr_for_pointer_param():
    type_map = _make_type_map("func_a", {
        "buf": {"c_type": "uint8_t*", "is_pointer": True, "is_const": False, "is_array": False, "struct_fields": {}},
    })
    sigs = _make_signatures("func_a")
    scenarios = _make_scenarios([
        {"function_name": "func_a", "scenario_id": "S001", "test_type": "NORMAL", "intent": "normal test"},
    ])
    result = fill_gaps(scenarios, type_map, sigs)
    tt_values = [s["test_type"] for s in result["scenarios"]]
    assert "NULL_PTR" in tt_values


def test_fill_gaps_adds_boundary_min_for_numeric():
    type_map = _make_type_map("func_b", {
        "count": {"c_type": "uint16_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_fields": {}},
    })
    sigs = _make_signatures("func_b", [{"name": "count", "type": "uint16_t"}])
    scenarios = _make_scenarios([
        {"function_name": "func_b", "scenario_id": "S001", "test_type": "NORMAL", "intent": "normal"},
    ])
    result = fill_gaps(scenarios, type_map, sigs)
    tt_values = [s["test_type"] for s in result["scenarios"]]
    assert "BOUNDARY_MIN" in tt_values


def test_fill_gaps_adds_boundary_max_for_numeric():
    type_map = _make_type_map("func_c", {
        "count": {"c_type": "uint16_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_fields": {}},
    })
    sigs = _make_signatures("func_c", [{"name": "count", "type": "uint16_t"}])
    scenarios = _make_scenarios([
        {"function_name": "func_c", "scenario_id": "S001", "test_type": "NORMAL", "intent": "normal"},
    ])
    result = fill_gaps(scenarios, type_map, sigs)
    tt_values = [s["test_type"] for s in result["scenarios"]]
    assert "BOUNDARY_MAX" in tt_values


def test_fill_gaps_adds_normal_for_function_without_one():
    type_map = _make_type_map("func_d")
    sigs = _make_signatures("func_d")
    scenarios = _make_scenarios([
        {"function_name": "func_d", "scenario_id": "S001", "test_type": "NULL_PTR", "intent": "null test"},
    ])
    result = fill_gaps(scenarios, type_map, sigs)
    tt_values = [s["test_type"] for s in result["scenarios"]]
    assert "NORMAL" in tt_values


def test_fill_gaps_no_duplicates_when_already_present():
    type_map = _make_type_map("func_e", {
        "buf": {"c_type": "uint8_t*", "is_pointer": True, "is_const": False, "is_array": False, "struct_fields": {}},
    })
    sigs = _make_signatures("func_e")
    scenarios = _make_scenarios([
        {"function_name": "func_e", "scenario_id": "S001", "test_type": "NORMAL", "intent": "normal"},
        {"function_name": "func_e", "scenario_id": "S002", "test_type": "NULL_PTR", "intent": "null"},
    ])
    result = fill_gaps(scenarios, type_map, sigs)
    null_count = sum(1 for s in result["scenarios"] if s["test_type"] == "NULL_PTR")
    assert null_count == 1


def test_fill_gaps_auto_generates_scenario_ids():
    type_map = _make_type_map("func_f")
    sigs = _make_signatures("func_f")
    scenarios = _make_scenarios([])
    result = fill_gaps(scenarios, type_map, sigs)
    gap_ids = [s["scenario_id"] for s in result["scenarios"] if s["scenario_id"].startswith("S_GAP_")]
    assert len(gap_ids) >= 1
    for gid in gap_ids:
        assert gid.startswith("S_GAP_"), f"Expected S_GAP_ prefix, got {gid}"


def test_fill_gaps_handles_string_input():
    type_map = _make_type_map("func_g")
    sigs = _make_signatures("func_g")
    scenarios_str = json.dumps({"scenarios": []})
    result = fill_gaps(scenarios_str, type_map, sigs)
    assert isinstance(result, dict)
    assert "scenarios" in result


def test_fill_gaps_multiple_functions():
    type_map = {
        "functions": {
            "func_x": {
                "params": {
                    "ptr": {"c_type": "uint8_t*", "is_pointer": True, "is_const": False, "is_array": False, "struct_fields": {}},
                },
            },
            "func_y": {
                "params": {
                    "val": {"c_type": "uint16_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_fields": {}},
                },
            },
        }
    }
    sigs = [
        {"name": "func_x", "params": [{"name": "ptr", "type": "uint8_t*"}]},
        {"name": "func_y", "params": [{"name": "val", "type": "uint16_t"}]},
    ]
    scenarios = _make_scenarios([])
    result = fill_gaps(scenarios, type_map, sigs)
    x_types = {s["test_type"] for s in result["scenarios"] if s["function_name"] == "func_x"}
    y_types = {s["test_type"] for s in result["scenarios"] if s["function_name"] == "func_y"}
    assert "NORMAL" in x_types
    assert "NULL_PTR" in x_types
    assert "NORMAL" in y_types
    assert "BOUNDARY_MIN" in y_types
    assert "BOUNDARY_MAX" in y_types


def test_validate_scenarios_valid_input():
    scenarios = _make_scenarios([
        {"function_name": "f", "scenario_id": "S001", "test_type": "NORMAL", "intent": "test"},
        {"function_name": "f", "scenario_id": "S002", "test_type": "NULL_PTR", "intent": "null"},
    ])
    errors = validate_scenarios(scenarios)
    assert errors == []


def test_validate_scenarios_missing_fields():
    scenarios = _make_scenarios([
        {"function_name": "f", "scenario_id": "S001"},
    ])
    errors = validate_scenarios(scenarios)
    assert any("test_type" in e for e in errors)


def test_validate_scenarios_invalid_test_type():
    scenarios = _make_scenarios([
        {"function_name": "f", "scenario_id": "S001", "test_type": "invalid", "intent": "test"},
    ])
    errors = validate_scenarios(scenarios)
    assert any("invalid" in e.lower() or "invalid test_type" in e for e in errors)


def test_validate_scenarios_duplicate_ids():
    scenarios = _make_scenarios([
        {"function_name": "f", "scenario_id": "S001", "test_type": "NORMAL", "intent": "test1"},
        {"function_name": "f", "scenario_id": "S001", "test_type": "NULL_PTR", "intent": "test2"},
    ])
    errors = validate_scenarios(scenarios)
    assert any("duplicate" in e.lower() for e in errors)
