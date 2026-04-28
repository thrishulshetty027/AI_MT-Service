"""Tests for stage2_generator.py — C code generation via templates."""

import json
import os
import shutil
import tempfile
import pytest

from src.schemas import TestCaseFile, TestCase, FunctionMeta, StubConfig, TestType
from src.stage2_generator import (
    load_testcase_file,
    build_test_case_ir,
    build_signatures_ir,
    render_test_script,
    render_header,
    write_stage2_outputs,
    run_stage2,
    _extract_type_map_from_testcases,
    GENERATED_TESTS_DIR,
)

SAMPLE_TYPE_MAP = {
    "functions": {
        "add_values": {
            "return_type": "uint8_t",
            "return_meaning": "sum",
            "return_valid_values": ["0u", "255u"],
            "params": {
                "a": {"c_type": "uint8_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_name": None, "struct_fields": {}, "valid_min": "0u", "valid_max": "255u"},
                "b": {"c_type": "uint8_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_name": None, "struct_fields": {}, "valid_min": "0u", "valid_max": "255u"},
            },
        }
    }
}


def _sample_tc_file():
    return TestCaseFile(
        pr_number="TEST01",
        module_name="module_TEST01",
        generated_at="2026-01-01T00:00:00+00:00",
        functions={
            "add_values": FunctionMeta(
                signature="uint8_t add_values(uint8_t a, uint8_t b)",
                return_type="uint8_t",
                description="Adds two values",
            ),
        },
        test_cases=[
            TestCase(
                scenario_id="S001",
                function_name="add_values",
                scenario="Normal add",
                test_type=TestType.NORMAL,
                inputs={"a": "10u", "b": "20u"},
                expected_return="30u",
            ),
            TestCase(
                scenario_id="S002",
                function_name="add_values",
                scenario="Boundary max",
                test_type=TestType.BOUNDARY_MAX,
                inputs={"a": "255u", "b": "255u"},
                expected_return="254u",
            ),
        ],
    )


class TestBuildTestCaseIR:

    def test_scalar_params_ir(self):
        tc_file = _sample_tc_file()
        tc = tc_file.test_cases[0]
        meta = tc_file.functions["add_values"]
        ir = build_test_case_ir(tc, meta, SAMPLE_TYPE_MAP)

        assert ir["scenario_id"] == "S001"
        assert ir["function_name"] == "add_values"
        assert ir["return_type"] == "uint8_t"
        assert len(ir["param_declarations"]) == 2
        assert ir["call_arguments"] == ["a", "b"]
        assert ir["expected_return"] == "30u"
        assert not ir["is_float_check"]
        assert not ir["has_struct"]

    def test_struct_params_ir(self):
        tc = TestCase(
            scenario_id="S003",
            function_name="process_act",
            scenario="Normal actuator",
            test_type=TestType.NORMAL,
            inputs={"act": {"field_a": "10u", "field_b": "FALSE"}},
            expected_return="E_OK",
        )
        meta = FunctionMeta(
            signature="Std_ReturnType process_act(Actuator_t act)",
            return_type="Std_ReturnType",
            description="Process actuator",
        )
        type_map = {
            "functions": {
                "process_act": {
                    "return_type": "Std_ReturnType",
                    "params": {
                        "act": {"c_type": "Actuator_t", "is_pointer": False, "struct_fields": {"field_a": "uint8_t", "field_b": "BOOL"}},
                    },
                }
            }
        }
        ir = build_test_case_ir(tc, meta, type_map)
        assert ir["has_struct"]
        assert len(ir["param_initializations"]) == 2
        assert ir["param_initializations"][0]["is_struct"]

    def test_pointer_params_ir(self):
        tc = TestCase(
            scenario_id="S004",
            function_name="check_ptr",
            scenario="NULL pointer test",
            test_type=TestType.NULL_PTR,
            inputs={"data": "NULL_PTR"},
            expected_return="E_NOT_OK",
        )
        meta = FunctionMeta(
            signature="Std_ReturnType check_ptr(uint8_t* data)",
            return_type="Std_ReturnType",
            description="Check pointer",
        )
        type_map = {
            "functions": {
                "check_ptr": {
                    "return_type": "Std_ReturnType",
                    "params": {
                        "data": {"c_type": "uint8_t*", "is_pointer": True},
                    },
                }
            }
        }
        ir = build_test_case_ir(tc, meta, type_map)
        assert ir["has_pointer"]
        assert "data" in ir["call_arguments"]


class TestBuildSignaturesIR:

    def test_builds_extern_signatures(self):
        tc_file = _sample_tc_file()
        sigs = build_signatures_ir(tc_file, SAMPLE_TYPE_MAP)
        assert len(sigs) == 1
        assert sigs[0]["name"] == "add_values"
        assert sigs[0]["return_type"] == "uint8_t"


class TestRenderTestScript:

    def test_renders_scalar_test_script(self):
        tc_file = _sample_tc_file()
        result = render_test_script(tc_file, SAMPLE_TYPE_MAP)

        assert '#include "module_TEST01.h"' in result
        assert "extern uint8_t add_values(" in result
        assert "void test_S001(void)" in result
        assert "void test_S002(void)" in result
        assert "result = add_values(a, b);" in result
        assert "CHECK_INT(30u, result);" in result
        assert "CHECK_INT(254u, result);" in result
        assert "int main(void)" in result
        assert "OPEN_LOG" in result
        assert "START_SCRIPT" in result

    def test_rendered_script_no_cpp_comments(self):
        tc_file = _sample_tc_file()
        result = render_test_script(tc_file, SAMPLE_TYPE_MAP)
        import re
        for line in result.split("\n"):
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
                continue
            assert " //" not in line, f"C++ comment found: {line}"

    def test_rendered_script_uses_FALSE_TRUE(self):
        tc_file = _sample_tc_file()
        result = render_test_script(tc_file, SAMPLE_TYPE_MAP)
        assert "FALSE" in result
        assert "TRUE" in result

    def test_struct_test_rendering(self):
        tc_file = TestCaseFile(
            pr_number="S1",
            module_name="module_S1",
            generated_at="now",
            functions={"process_act": FunctionMeta(signature="Std_ReturnType process_act(Actuator_t act)", return_type="Std_ReturnType", description="Process")},
            test_cases=[
                TestCase(
                    scenario_id="S001",
                    function_name="process_act",
                    scenario="Normal",
                    test_type=TestType.NORMAL,
                    inputs={"act": {"field_a": "10u", "field_b": "FALSE"}},
                    expected_return="E_OK",
                ),
            ],
        )
        type_map = {
            "functions": {
                "process_act": {
                    "return_type": "Std_ReturnType",
                    "params": {"act": {"c_type": "Actuator_t", "is_pointer": False, "struct_fields": {"field_a": "uint8_t", "field_b": "BOOL"}}},
                }
            }
        }
        result = render_test_script(tc_file, type_map)
        assert "act.field_a = 10u;" in result
        assert "act.field_b = FALSE;" in result


class TestRenderHeader:

    def test_renders_header(self):
        tc_file = _sample_tc_file()
        result = render_header(tc_file, SAMPLE_TYPE_MAP)
        assert "#ifndef MODULE_TEST01_H_" in result
        assert "extern uint8_t add_values(" in result
        assert "#endif" in result


class TestWriteStage2Outputs:

    def setup_method(self):
        if os.path.exists(GENERATED_TESTS_DIR):
            shutil.rmtree(GENERATED_TESTS_DIR)

    def teardown_method(self):
        if os.path.exists(GENERATED_TESTS_DIR):
            shutil.rmtree(GENERATED_TESTS_DIR)

    def test_writes_c_and_h_files(self):
        tc_file = _sample_tc_file()
        written = write_stage2_outputs(tc_file, SAMPLE_TYPE_MAP)
        assert os.path.exists(written["test_script_c"])
        assert os.path.exists(written["header_h"])
        assert written["test_script_c"].endswith(".c")
        assert written["header_h"].endswith(".h")


class TestRunStage2:

    def setup_method(self):
        if os.path.exists(GENERATED_TESTS_DIR):
            shutil.rmtree(GENERATED_TESTS_DIR)

    def teardown_method(self):
        if os.path.exists(GENERATED_TESTS_DIR):
            shutil.rmtree(GENERATED_TESTS_DIR)

    def test_run_stage2_from_json_file(self):
        tc_file = _sample_tc_file()
        tmpdir = tempfile.mkdtemp()
        try:
            json_path = os.path.join(tmpdir, "testcases.json")
            with open(json_path, "w") as f:
                f.write(tc_file.model_dump_json(indent=2))

            result = run_stage2(json_path, SAMPLE_TYPE_MAP)
            assert result["test_cases_loaded"] == 2
            assert result["functions_count"] == 1
            assert os.path.exists(result["test_script_c"])
            assert os.path.exists(result["header_h"])
        finally:
            shutil.rmtree(tmpdir)

    def test_run_stage2_auto_type_map(self):
        tc_file = _sample_tc_file()
        tmpdir = tempfile.mkdtemp()
        try:
            json_path = os.path.join(tmpdir, "testcases.json")
            with open(json_path, "w") as f:
                f.write(tc_file.model_dump_json(indent=2))

            result = run_stage2(json_path)
            assert result["test_cases_loaded"] == 2
        finally:
            shutil.rmtree(tmpdir)


class TestLoadTestcaseFile:

    def test_load_valid_json(self):
        tc_file = _sample_tc_file()
        tmpdir = tempfile.mkdtemp()
        try:
            json_path = os.path.join(tmpdir, "testcases.json")
            with open(json_path, "w") as f:
                f.write(tc_file.model_dump_json(indent=2))
            loaded = load_testcase_file(json_path)
            assert loaded.pr_number == "TEST01"
            assert len(loaded.test_cases) == 2
        finally:
            shutil.rmtree(tmpdir)

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_testcase_file("/nonexistent/path.json")
