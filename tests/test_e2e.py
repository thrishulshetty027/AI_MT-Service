"""E2E tests — full pipeline from diff to generated C files."""

import json
import os
import shutil
import threading
import pytest
from unittest.mock import patch

from src.schemas import TestCaseFile, TestCase, FunctionMeta, TestType
from src.stage2_generator import GENERATED_TESTS_DIR

SAMPLE_DIFF = """diff --git a/module.c b/module.c
--- a/module.c
+++ b/module.c
@@ -1,3 +1,10 @@
+#include <stdint.h>
+
+uint8_t add_values(uint8_t a, uint8_t b) {
+    uint8_t result = a + b;
+    return result;
+}
"""

SAMPLE_TYPE_MAP = {
    "functions": {
        "add_values": {
            "return_type": "uint8_t",
            "return_meaning": "sum of inputs",
            "return_valid_values": ["0u", "255u"],
            "params": {
                "a": {"c_type": "uint8_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_name": None, "struct_fields": {}, "valid_min": "0u", "valid_max": "255u", "null_value": "0u"},
                "b": {"c_type": "uint8_t", "is_pointer": False, "is_const": False, "is_array": False, "struct_name": None, "struct_fields": {}, "valid_min": "0u", "valid_max": "255u", "null_value": "0u"},
            },
        }
    }
}

SAMPLE_COMPLEXITY = {
    "classifications": {
        "add_values": {"tier": "TIER_1_AUTO", "cyclomatic_score": 1, "param_count": 2, "hw_coupled": False, "os_coupled": False}
    }
}

SAMPLE_SCENARIOS_RAW = {
    "scenarios": [
        {"function_name": "add_values", "scenario_id": "S001", "scenario_name": "Normal add", "intent": "Verify addition", "test_type": "NORMAL", "branch_targeted": None, "expected_behavior": "Returns sum"},
        {"function_name": "add_values", "scenario_id": "S002", "scenario_name": "Boundary max", "intent": "Verify max boundary", "test_type": "BOUNDARY_MAX", "branch_targeted": None, "expected_behavior": "Handles max"},
    ]
}

SAMPLE_SCENARIOS_FINAL = {
    "scenarios": [
        {"function_name": "add_values", "scenario_id": "S001", "scenario_name": "Normal add", "intent": "Verify addition", "test_type": "NORMAL", "branch_targeted": None, "expected_behavior": "Returns sum"},
        {"function_name": "add_values", "scenario_id": "S002", "scenario_name": "Boundary max", "intent": "Verify max boundary", "test_type": "BOUNDARY_MAX", "branch_targeted": None, "expected_behavior": "Handles max"},
    ],
    "coverage_summary": {"add_values": {"total_scenarios": 2, "branches_covered": [], "mc_dc_complete": True}},
}

SAMPLE_VALUES_FINAL = {
    "test_cases": [
        {"scenario_id": "S001", "function_name": "add_values", "inputs": {"a": "10u", "b": "20u"}, "expected_return": "30u", "expected_output_params": {}, "needs_human_review": False, "human_review_reason": None},
        {"scenario_id": "S002", "function_name": "add_values", "inputs": {"a": "255u", "b": "255u"}, "expected_return": "254u", "expected_output_params": {}, "needs_human_review": False, "human_review_reason": None},
    ],
    "needs_human_count": 0,
    "corrections_applied": 0,
}

SAMPLE_ASSEMBLED = {
    "version": "1.0",
    "pr_number": "E2E01",
    "module_name": "module_E2E01",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "functions": {
        "add_values": {
            "signature": "uint8_t add_values(uint8_t a, uint8_t b)",
            "return_type": "uint8_t",
            "description": "Adds two values",
            "asil_level": "ASIL_B",
        }
    },
    "hal_stubs": [],
    "test_cases": [
        {
            "scenario_id": "S001",
            "function_name": "add_values",
            "scenario": "Normal add",
            "test_type": "NORMAL",
            "inputs": {"a": "10u", "b": "20u"},
            "expected_return": "30u",
            "expected_output_params": {},
            "stubs": {},
            "asil_level": "ASIL_B",
            "requirement_ref": "",
        },
        {
            "scenario_id": "S002",
            "function_name": "add_values",
            "scenario": "Boundary max",
            "test_type": "BOUNDARY_MAX",
            "inputs": {"a": "255u", "b": "255u"},
            "expected_return": "254u",
            "expected_output_params": {},
            "stubs": {},
            "asil_level": "ASIL_B",
            "requirement_ref": "",
        },
    ],
}


def _mock_llm_responses():
    return iter([
        "add_values computes the sum of two uint8 values.",
        json.dumps(SAMPLE_TYPE_MAP),
        json.dumps(SAMPLE_COMPLEXITY),
        json.dumps(SAMPLE_SCENARIOS_RAW),
        json.dumps({"issues": [], "scenarios_to_add": [], "scenario_ids_to_remove": []}),
        json.dumps(SAMPLE_SCENARIOS_FINAL),
        json.dumps({"test_cases": SAMPLE_VALUES_FINAL["test_cases"]}),
        json.dumps({"fixes": []}),
        json.dumps(SAMPLE_VALUES_FINAL),
        json.dumps({"stub_configs": [{"scenario_id": "S001", "stubs": {}}, {"scenario_id": "S002", "stubs": {}}]}),
        json.dumps({"stub_configs": [{"scenario_id": "S001", "stubs": {}}, {"scenario_id": "S002", "stubs": {}}]}),
        json.dumps(SAMPLE_ASSEMBLED),
        json.dumps({"self_review": {"scenarios_planned": 2, "test_cases_generated": 2, "issues_found": [], "issues_fixed": []}, **SAMPLE_ASSEMBLED}),
    ])


class _ThreadSafeMock:
    def __init__(self, responses_iter):
        self._lock = threading.Lock()
        self._iter = responses_iter

    def __call__(self, prompt):
        with self._lock:
            return next(self._iter)


class TestE2EFullPipeline:

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_full_pipeline_produces_all_outputs(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())

        from src.stage1_generator import run_stage1
        from src.stage2_generator import run_stage2
        from src.quality_gates import generate_traceability, write_trace

        tc_file, state = run_stage1(SAMPLE_DIFF, "E2E01")

        assert os.path.exists(os.path.join(GENERATED_TESTS_DIR, "pr_E2E01_testcases.md"))
        assert os.path.exists(os.path.join(GENERATED_TESTS_DIR, "pr_E2E01_testcases.json"))

        json_path = os.path.join(GENERATED_TESTS_DIR, "pr_E2E01_testcases.json")
        result = run_stage2(json_path, state.type_map)

        assert os.path.exists(result["test_script_c"])
        assert os.path.exists(result["header_h"])
        assert result["test_script_c"].endswith(".c")
        assert result["header_h"].endswith(".h")

        tc_dict = json.loads(tc_file.model_dump_json())
        trace = generate_traceability(tc_dict, "E2E01", tc_file.module_name)
        trace_path = write_trace(trace, "E2E01")
        assert os.path.exists(trace_path)

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_generated_c_file_is_valid_c89(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())

        from src.stage1_generator import run_stage1
        from src.stage2_generator import run_stage2

        tc_file, state = run_stage1(SAMPLE_DIFF, "E2E02")
        json_path = os.path.join(GENERATED_TESTS_DIR, "pr_E2E02_testcases.json")
        result = run_stage2(json_path, state.type_map)

        with open(result["test_script_c"], "r") as f:
            c_content = f.read()

        assert "int main(void)" in c_content
        assert "OPEN_LOG" in c_content
        assert "START_SCRIPT" in c_content
        assert "CHECK_INT" in c_content
        assert "void test_S001(void)" in c_content
        assert "void test_S002(void)" in c_content
        assert "//" not in c_content.split("/*")[0]
        assert "FALSE" in c_content
        assert "TRUE" in c_content

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_generated_json_matches_schema(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())

        from src.stage1_generator import run_stage1

        tc_file, state = run_stage1(SAMPLE_DIFF, "E2E03")

        json_path = os.path.join(GENERATED_TESTS_DIR, "pr_E2E03_testcases.json")
        with open(json_path, "r") as f:
            data = json.loads(f.read())

        loaded = TestCaseFile(**data)
        assert loaded.pr_number == "E2E03"
        assert len(loaded.test_cases) >= 1
        errors = loaded.validate_internal_consistency()
        assert errors == []

    def test_stage2_only_regenerates_from_json(self):
        from src.stage2_generator import run_stage2

        os.makedirs(GENERATED_TESTS_DIR, exist_ok=True)
        tc_file = TestCaseFile(
            pr_number="E2E04",
            module_name="module_E2E04",
            generated_at="2026-01-01T00:00:00+00:00",
            functions={"add_values": FunctionMeta(signature="uint8_t add_values(uint8_t a, uint8_t b)", return_type="uint8_t", description="add")},
            test_cases=[
                TestCase(scenario_id="S001", function_name="add_values", scenario="Normal", test_type=TestType.NORMAL, inputs={"a": "5u", "b": "10u"}, expected_return="15u"),
            ],
        )
        json_path = os.path.join(GENERATED_TESTS_DIR, "pr_E2E04_testcases.json")
        with open(json_path, "w") as f:
            f.write(tc_file.model_dump_json(indent=2))

        result = run_stage2(json_path, SAMPLE_TYPE_MAP)

        assert os.path.exists(result["test_script_c"])
        assert os.path.exists(result["header_h"])
        with open(result["test_script_c"], "r") as f:
            c_content = f.read()
        assert "CHECK_INT(15u, result)" in c_content

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_traceability_sidecar_complete(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())

        from src.stage1_generator import run_stage1
        from src.quality_gates import generate_traceability, write_trace

        tc_file, state = run_stage1(SAMPLE_DIFF, "E2E05")
        tc_dict = json.loads(tc_file.model_dump_json())
        trace = generate_traceability(tc_dict, "E2E05", tc_file.module_name)
        trace_path = write_trace(trace, "E2E05")

        with open(trace_path, "r") as f:
            trace_data = json.loads(f.read())

        assert trace_data["standard"] == "ISO 26262"
        assert trace_data["asil_level"] == "ASIL_B"
        assert trace_data["pr_number"] == "E2E05"
        assert trace_data["summary"]["total_test_cases"] >= 1
        assert "add_values" in trace_data["function_coverage"]
        assert "test_type_distribution" in trace_data

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_markdown_contains_engineer_checklist(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())

        from src.stage1_generator import run_stage1

        run_stage1(SAMPLE_DIFF, "E2E06")

        md_path = os.path.join(GENERATED_TESTS_DIR, "pr_E2E06_testcases.md")
        with open(md_path, "r") as f:
            md_content = f.read()

        assert "## Engineer Review Checklist" in md_content
        assert "- [ ] Struct field names correct" in md_content
        assert "- [ ] Boundary values match hardware constraints" in md_content
        assert "- [ ] HAL stubs correctly identified" in md_content
        assert "- [ ] Expected returns correct" in md_content
        assert "- [ ] MC/DC coverage adequate" in md_content
