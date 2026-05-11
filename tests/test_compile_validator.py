"""Tests for compile_validator.py and quality_gates.py."""

import json
import os
import shutil
import pytest

from src.compile_validator import (
    parse_msvc_errors,
    fix_ir_for_error,
    apply_ir_fixes,
    compile_with_msvc,
    write_compile_report,
)
from src.quality_gates import (
    run_cppcheck,
    generate_traceability,
    write_trace,
)


class TestParseMsvcErrors:

    def test_parses_single_error(self):
        output = 'test_module.c(42): error C2039: \'pressure\': is not a member of \'Actuator_t\''
        errors = parse_msvc_errors(output)
        assert len(errors) == 1
        assert errors[0]["error_code"] == "C2039"
        assert errors[0]["line"] == "42"
        assert "pressure" in errors[0]["message"]

    def test_parses_multiple_errors(self):
        output = (
            'test.c(10): error C2065: \'foo\': undeclared identifier\n'
            'test.c(20): error C4013: \'bar\': undefined function\n'
        )
        errors = parse_msvc_errors(output)
        assert len(errors) == 2
        assert errors[0]["error_code"] == "C2065"
        assert errors[1]["error_code"] == "C4013"

    def test_parses_no_errors(self):
        errors = parse_msvc_errors("Build succeeded.")
        assert errors == []


class TestFixIrForError:

    def test_c2039_wrong_struct_field(self):
        error = {"error_code": "C2039", "message": "'pressure': is not a member of 'Actuator_t'", "line": "10", "file": "test.c"}
        fix = fix_ir_for_error(error, {}, [])
        assert fix is not None
        assert fix["fix_type"] == "wrong_struct_field"
        assert fix["field_name"] == "pressure"

    def test_c2065_undeclared_identifier(self):
        error = {"error_code": "C2065", "message": "'my_var': undeclared identifier", "line": "5", "file": "test.c"}
        fix = fix_ir_for_error(error, {}, [])
        assert fix is not None
        assert fix["fix_type"] == "undeclared_identifier"
        assert fix["identifier"] == "my_var"

    def test_c2143_template_bug(self):
        error = {"error_code": "C2143", "message": "syntax error: missing ';' before 'type'", "line": "15", "file": "test.c"}
        fix = fix_ir_for_error(error, {}, [])
        assert fix is not None
        assert fix["fix_type"] == "declaration_after_statement"

    def test_c4013_undefined_function(self):
        error = {"error_code": "C4013", "message": "'HAL_Read': undefined function", "line": "8", "file": "test.c"}
        fix = fix_ir_for_error(error, {}, [])
        assert fix is not None
        assert fix["fix_type"] == "undefined_function"
        assert fix["function_name"] == "HAL_Read"

    def test_unknown_error_code_returns_none(self):
        error = {"error_code": "C9999", "message": "unknown error", "line": "1", "file": "test.c"}
        fix = fix_ir_for_error(error, {}, [])
        assert fix is None


class TestApplyIrFixes:

    def test_removes_wrong_struct_field(self):
        fixes = [{"fix_type": "wrong_struct_field", "field_name": "pressure"}]
        irs = [{"inputs": {"act": {"field_a": "10u", "pressure": "99u"}}, "param_initializations": []}]
        _, updated_irs, _ = apply_ir_fixes(fixes, {}, irs, [])
        assert "pressure" not in updated_irs[0]["inputs"]["act"]

    def test_adds_extern_for_undeclared(self):
        fixes = [{"fix_type": "undeclared_identifier", "identifier": "HAL_Read"}]
        _, _, updated_sigs = apply_ir_fixes(fixes, {}, [], [])
        assert any(s["name"] == "HAL_Read" for s in updated_sigs)

    def test_template_bug_stops_fixing(self):
        fixes = [{"fix_type": "declaration_after_statement", "description": "bug"}]
        _, _, _ = apply_ir_fixes(fixes, {}, [], [])


class TestCompileWithMsvc:

    def test_cl_not_found_returns_skipped(self):
        result = compile_with_msvc("nonexistent.c", cl_exe="nonexistent_cl.exe")
        assert result.get("skipped") is True


class TestWriteCompileReport:

    def test_writes_report(self):
        result = {
            "compile_report": {
                "attempts": 2,
                "errors_fixed": ["removed field 'pressure'"],
                "final_errors": [],
            }
        }
        path = write_compile_report("T1", result)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["attempts"] == 2


class TestRunCppcheck:

    def test_cppcheck_not_found_returns_skipped(self):
        result = run_cppcheck("test.c", cppcheck_exe="nonexistent_cppcheck")
        assert result.get("skipped") is True


class TestGenerateTraceability:

    def test_generates_trace(self):
        tc_dict = {
            "pr_number": "T1",
            "module_name": "module_T1",
            "functions": {"add_values": {"signature": "uint8_t add_values(uint8_t a, uint8_t b)", "return_type": "uint8_t", "description": "add"}},
            "test_cases": [
                {"scenario_id": "S001", "function_name": "add_values", "test_type": "NORMAL"},
                {"scenario_id": "S002", "function_name": "add_values", "test_type": "BOUNDARY_MAX"},
            ],
            "hal_stubs": ["HAL_Read"],
        }
        trace = generate_traceability(tc_dict, "T1", "module_T1")
        assert trace["pr_number"] == "T1"
        assert trace["summary"]["total_test_cases"] == 2
        assert trace["summary"]["hal_stubs"] == ["HAL_Read"]
        assert "add_values" in trace["function_coverage"]
        assert trace["function_coverage"]["add_values"]["total_scenarios"] == 2
        assert trace["test_type_distribution"]["NORMAL"] == 1

    def test_trace_with_quality_gates(self):
        trace = generate_traceability(
            {"test_cases": [], "functions": {}, "hal_stubs": []},
            "T2", "module_T2",
            compile_result={"success": True, "attempts": 1},
            cppcheck_result={"issue_count": 0, "skipped": False},
        )
        assert trace["quality_gates"]["compile_success"] is True
        assert trace["quality_gates"]["cppcheck_issues"] == 0


class TestWriteTrace:

    def test_writes_trace_json(self):
        trace = {"pr_number": "T1", "module_name": "module_T1"}
        path = write_trace(trace, "T1")
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["pr_number"] == "T1"
