"""Tests for Jinja2 template rendering — C89 compliance verification."""

import os
import re
import pytest
import jinja2

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
PARTIALS_DIR = os.path.join(TEMPLATE_DIR, "partials")


def _render(template_path, **context):
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.dirname(template_path)),
        keep_trailing_newline=True,
    )
    template = env.from_string(template_str)
    return template.render(**context)


def _sample_tc(**overrides):
    tc = {
        "scenario_id": "S001",
        "function_name": "add_values",
        "scenario": "Normal add test",
        "test_type": "NORMAL",
        "intent": "Verify addition",
        "inputs": {"a": "10u", "b": "20u"},
        "expected_return": "30u",
        "expected_output_params": {},
        "stubs": {},
        "return_type": "uint8_t",
        "call_arguments": ["a", "b"],
        "param_declarations": [
            {"name": "a", "ctype": "uint8_t"},
            {"name": "b", "ctype": "uint8_t"},
        ],
        "param_initializations": [
            {"name": "a", "value": "10u"},
            {"name": "b", "value": "20u"},
        ],
        "is_float_check": False,
    }
    tc.update(overrides)
    return tc


def _sample_sig():
    return {
        "name": "add_values",
        "return_type": "uint8_t",
        "params": ["uint8_t a", "uint8_t b"],
        "is_static": False,
    }


class TestMasterTemplate:

    def test_renders_complete_test_script(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_TEST01",
            pr_number="TEST01",
            timestamp="2026-01-01T00:00:00",
            function_signatures=[_sample_sig()],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )
        assert '#include "module_TEST01.h"' in result
        assert "extern uint8_t add_values(uint8_t a, uint8_t b);" in result
        assert "void test_S001(void);" in result
        assert "void test_S001(void)" in result
        assert "result = add_values(a, b);" in result
        assert "CHECK_INT(30u, result);" in result

    def test_c89_no_double_slash_comments(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[_sample_sig()],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )
        for line in result.split("\n"):
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
                continue
            assert not re.match(r"^.*//", stripped), f"Found C++ comment: {stripped}"

    def test_uses_FALSE_TRUE_not_false_true(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )
        assert "OPEN_LOG" in result
        assert "FALSE" in result
        assert "TRUE" in result
        assert "false" not in result.split("OPEN_LOG")[1].split(")")[0]
        assert "START_SCRIPT" in result

    def test_void_main_has_void_parameter(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )
        assert "int main(void)" in result
        assert "void run_tests(void)" in result

    def test_includes_math_h_when_float_tests(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=True,
            test_cases=[_sample_tc()],
        )
        assert "#include <math.h>" in result

    def test_no_math_h_when_no_float_tests(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )
        assert "#include <math.h>" not in result

    def test_stub_setup_rendered(self):
        tc = _sample_tc(stubs={
            "HAL_ADC_Read": {
                "return_value": "HAL_OK",
                "expected_call_count": 1,
                "output_params": {"pData": "12000u"},
            }
        })
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=["HAL_ADC_Read"],
            has_float_tests=False,
            test_cases=[tc],
        )
        assert "INITIALISE_STUB_RETURN(HAL_ADC_Read, HAL_OK);" in result
        assert "INITIALISE_STUB_POINTER_PARAM(HAL_ADC_Read, pData, 12000u);" in result
        assert "CHECK_N_CALLS(HAL_ADC_Read, 1);" in result

    def test_void_return_test(self):
        tc = _sample_tc(
            return_type="void",
            function_name="process_data",
            expected_output_params={"status": "E_OK"},
        )
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[tc],
        )
        assert "(void)process_data(" in result
        assert "CHECK_INT(E_OK, status);" in result

    def test_float_return_uses_check_double(self):
        tc = _sample_tc(
            return_type="float",
            is_float_check=True,
            float_tolerance="0.001f",
            expected_return="3.14f",
        )
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
            hal_stubs=[],
            has_float_tests=True,
            test_cases=[tc],
        )
        assert "CHECK_DOUBLE(3.14f, result, 0.001f);" in result

    def test_multiple_test_cases(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[_sample_sig()],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc(scenario_id="S001"), _sample_tc(scenario_id="S002")],
        )
        assert "void test_S001(void);" in result
        assert "void test_S002(void);" in result
        assert "test_S001();" in result
        assert "test_S002();" in result


class TestHeaderTemplate:

    def test_renders_header_with_extern(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_header.h.j2"),
            module_name="module_TEST01",
            pr_number="TEST01",
            timestamp="now",
            function_signatures=[_sample_sig()],
        )
        assert "#ifndef MODULE_TEST01_H_" in result
        assert "extern uint8_t add_values(uint8_t a, uint8_t b);" in result
        assert "#include <stdint.h>" in result

    def test_header_include_guard(self):
        result = _render(
            os.path.join(TEMPLATE_DIR, "cantata_header.h.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[],
        )
        assert "#ifndef MODULE_T_H_" in result
        assert "#define MODULE_T_H_" in result
        assert "#endif /* MODULE_T_H_ */" in result


class TestPartialTemplates:

    def test_scalar_partial(self):
        result = _render(
            os.path.join(PARTIALS_DIR, "_scalar_test.c.j2"),
            tc=_sample_tc(),
            param_ctypes={"a": "uint8_t", "b": "uint8_t"},
            call_args=["a", "b"],
        )
        assert "uint8_t a = 10u;" in result
        assert "uint8_t b = 20u;" in result
        assert "result = add_values(a, b);" in result
        assert "CHECK_INT(30u, result);" in result

    def test_struct_partial(self):
        tc = _sample_tc(
            inputs={"act": {"field_a": "10u", "field_b": "FALSE"}},
            function_name="process_actuator",
            call_arguments=["act"],
        )
        result = _render(
            os.path.join(PARTIALS_DIR, "_struct_test.c.j2"),
            tc=tc,
            param_name="act",
            struct_name="Actuator_t",
            struct_type="Actuator_t",
            call_args=["act"],
        )
        assert "Actuator_t act;" in result
        assert "act.field_a = 10u;" in result
        assert "act.field_b = FALSE;" in result

    def test_pointer_partial(self):
        tc = _sample_tc(
            inputs={"ptr": "NULL_PTR"},
            function_name="check_ptr",
            call_arguments=["ptr"],
            expected_return="E_NOT_OK",
        )
        result = _render(
            os.path.join(PARTIALS_DIR, "_pointer_test.c.j2"),
            tc=tc,
            param_name="ptr",
            param_ctype="uint8_t*",
            base_type="uint8_t",
            param_value="NULL_PTR",
            call_args=["ptr"],
        )
        assert "uint8_t* ptr = NULL_PTR;" in result
        assert "CHECK_INT(E_NOT_OK, result);" in result

    def test_array_partial(self):
        tc = _sample_tc(
            inputs={"data": "{1u, 2u, 3u}"},
            function_name="process_array",
            call_arguments=["data", "data_size"],
        )
        result = _render(
            os.path.join(PARTIALS_DIR, "_array_test.c.j2"),
            tc=tc,
            param_name="data",
            base_type="uint8_t",
            array_values=["1u", "2u", "3u"],
            array_size="3",
            call_args=["data", "data_size"],
        )
        assert "uint8_t data[] = { 1u, 2u, 3u };" in result
        assert "uint16_t data_size = 3u;" in result

    def test_float_partial(self):
        tc = _sample_tc(
            return_type="float",
            inputs={"x": "3.14f"},
            expected_return="6.28f",
            function_name="double_val",
            call_arguments=["x"],
        )
        result = _render(
            os.path.join(PARTIALS_DIR, "_float_test.c.j2"),
            tc=tc,
            param_ctypes={"x": "float"},
            call_args=["x"],
            tolerance="0.001f",
        )
        assert "float x = 3.14f;" in result
        assert "CHECK_DOUBLE(6.28f, result, 0.001f);" in result

    def test_void_return_partial(self):
        tc = _sample_tc(
            return_type="void",
            function_name="set_flag",
            inputs={"flag": "TRUE"},
            call_arguments=["flag"],
            expected_output_params={"status": "1u"},
        )
        result = _render(
            os.path.join(PARTIALS_DIR, "_void_return_test.c.j2"),
            tc=tc,
            param_ctypes={"flag": "uint8_t"},
            call_args=["flag"],
        )
        assert "set_flag(flag);" in result
        assert "CHECK_INT(1u, status);" in result

    def test_stub_setup_partial(self):
        tc = _sample_tc(stubs={
            "HAL_Read": {"return_value": "HAL_OK", "expected_call_count": 2, "output_params": {"buf": "0u"}},
        })
        result = _render(
            os.path.join(PARTIALS_DIR, "_stub_setup.c.j2"),
            tc=tc,
        )
        assert "INITIALISE_STUB_RETURN(HAL_Read, HAL_OK);" in result
        assert "INITIALISE_STUB_POINTER_PARAM(HAL_Read, buf, 0u);" in result

    def test_main_partial(self):
        tc1 = _sample_tc(scenario_id="S001")
        tc2 = _sample_tc(scenario_id="S002")
        result = _render(
            os.path.join(PARTIALS_DIR, "_main.c.j2"),
            module_name="module_T",
            pr_number="T",
            test_cases=[tc1, tc2],
        )
        assert "test_S001();" in result
        assert "test_S002();" in result
        assert "OPEN_LOG" in result
        assert "START_SCRIPT" in result
        assert "rule_set" in result


class TestC89Compliance:

    def _render_full(self):
        return _render(
            os.path.join(TEMPLATE_DIR, "cantata_test.c.j2"),
            module_name="module_T",
            pr_number="T",
            timestamp="now",
            function_signatures=[_sample_sig()],
            hal_stubs=[],
            has_float_tests=False,
            test_cases=[_sample_tc()],
        )

    def test_no_c99_comments(self):
        result = self._render_full()
        lines = result.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.endswith("*/"):
                continue
            if stripped.startswith("*"):
                continue
            assert " //" not in line, f"C++ comment on line {i+1}: {line}"

    def test_false_true_capitalized(self):
        result = self._render_full()
        assert "FALSE" in result
        assert "TRUE" in result
        open_log_line = [l for l in result.split("\n") if "OPEN_LOG" in l]
        assert len(open_log_line) > 0
        assert "FALSE" in open_log_line[0]

    def test_null_ptr_not_null(self):
        result = _render(
            os.path.join(PARTIALS_DIR, "_pointer_test.c.j2"),
            tc=_sample_tc(
                inputs={"ptr": "NULL_PTR"},
                function_name="check_ptr",
                call_arguments=["ptr"],
            ),
            param_name="ptr",
            param_ctype="uint8_t*",
            base_type="uint8_t",
            param_value="NULL_PTR",
            call_args=["ptr"],
        )
        assert "NULL_PTR" in result
        assert " NULL " not in result
