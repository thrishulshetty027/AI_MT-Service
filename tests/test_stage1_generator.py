"""Tests for stage1_generator.py — Stage 1 pipeline orchestrator."""

import json
import os
import shutil
import threading
import pytest
from unittest.mock import patch, MagicMock

from src.multi_call_pipeline import PipelineState
from src.schemas import TestCaseFile, TestCase, FunctionMeta, StubConfig, TestType
from src.stage1_generator import (
    prepare_pipeline_state,
    run_stage1_with_validators,
    extract_testcase_file,
    generate_testcases_markdown,
    write_outputs,
    run_stage1,
    GENERATED_TESTS_DIR,
)

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
        {"function_name": "add_values", "scenario_id": "S001", "scenario_name": "Normal add", "intent": "Verify normal addition", "test_type": "NORMAL", "branch_targeted": None, "expected_behavior": "Returns sum"},
    ]
}

SAMPLE_SCENARIOS_CRITIQUE = {
    "issues": [],
    "scenarios_to_add": [],
    "scenario_ids_to_remove": [],
}

SAMPLE_SCENARIOS_FINAL = {
    "scenarios": [
        {"function_name": "add_values", "scenario_id": "S001", "scenario_name": "Normal add", "intent": "Verify normal addition", "test_type": "NORMAL", "branch_targeted": None, "expected_behavior": "Returns sum"},
    ],
    "coverage_summary": {"add_values": {"total_scenarios": 1, "branches_covered": [], "mc_dc_complete": True}},
}

SAMPLE_VALUES_RAW = {
    "test_cases": [
        {"scenario_id": "S001", "function_name": "add_values", "inputs": {"a": "10u", "b": "20u"}, "expected_return": "30u", "expected_output_params": {}},
    ]
}

SAMPLE_VALUES_CRITIQUE = {"fixes": []}

SAMPLE_VALUES_FINAL = {
    "test_cases": [
        {"scenario_id": "S001", "function_name": "add_values", "inputs": {"a": "10u", "b": "20u"}, "expected_return": "30u", "expected_output_params": {}, "needs_human_review": False, "human_review_reason": None},
    ],
    "needs_human_count": 0,
    "corrections_applied": 0,
}

SAMPLE_STUBS_RAW = {"stub_configs": [{"scenario_id": "S001", "stubs": {}}]}

SAMPLE_STUBS_FINAL = {"stub_configs": [{"scenario_id": "S001", "stubs": {}}]}

SAMPLE_ASSEMBLED_JSON = {
    "version": "1.0",
    "pr_number": "TEST01",
    "module_name": "module_TEST01",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "functions": {
        "add_values": {
            "signature": "uint8_t add_values(uint8_t a, uint8_t b)",
            "return_type": "uint8_t",
            "description": "Adds two uint8 values",
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
        }
    ],
}

SAMPLE_SELF_REVIEW = {
    "self_review": {
        "scenarios_planned": 1,
        "test_cases_generated": 1,
        "issues_found": [],
        "issues_fixed": [],
        "fields_removed": [],
        "stubs_added": [],
        "values_corrected": [],
    },
    **SAMPLE_ASSEMBLED_JSON,
}


def _make_state_with_all_outputs():
    state = PipelineState(
        diff_text=SAMPLE_DIFF,
        pr_number="TEST01",
        module_name="module_TEST01",
        function_signatures=[{"name": "add_values", "params": [{"name": "a", "type": "uint8_t"}, {"name": "b", "type": "uint8_t"}]}],
        struct_definitions={},
        typedef_map={},
        macro_constants={},
        hal_functions=[],
        code_analysis="add_values computes the sum of two uint8 values.",
        type_map=SAMPLE_TYPE_MAP,
        complexity_tiers=SAMPLE_COMPLEXITY,
        scenarios_raw=SAMPLE_SCENARIOS_RAW,
        scenarios_critique=SAMPLE_SCENARIOS_CRITIQUE,
        scenarios_final=SAMPLE_SCENARIOS_FINAL,
        values_raw=SAMPLE_VALUES_RAW,
        values_critique=SAMPLE_VALUES_CRITIQUE,
        values_final=SAMPLE_VALUES_FINAL,
        stubs_raw=SAMPLE_STUBS_RAW,
        stubs_final=SAMPLE_STUBS_FINAL,
        assembled_json=SAMPLE_ASSEMBLED_JSON,
        self_review_result=SAMPLE_SELF_REVIEW,
    )
    return state


def _mock_llm_responses():
    return iter([
        "add_values computes sum of two uint8 values.",
        json.dumps(SAMPLE_TYPE_MAP),
        json.dumps(SAMPLE_COMPLEXITY),
        json.dumps(SAMPLE_SCENARIOS_RAW),
        json.dumps(SAMPLE_SCENARIOS_CRITIQUE),
        json.dumps(SAMPLE_SCENARIOS_FINAL),
        json.dumps(SAMPLE_VALUES_RAW),
        json.dumps(SAMPLE_VALUES_CRITIQUE),
        json.dumps(SAMPLE_VALUES_FINAL),
        json.dumps(SAMPLE_STUBS_RAW),
        json.dumps(SAMPLE_STUBS_FINAL),
        json.dumps(SAMPLE_ASSEMBLED_JSON),
        json.dumps(SAMPLE_SELF_REVIEW),
    ])


class _ThreadSafeMock:
    """Mock that returns values from a shared iterator safely across threads."""

    def __init__(self, responses_iter):
        self._lock = threading.Lock()
        self._iter = responses_iter

    def __call__(self, prompt):
        with self._lock:
            return next(self._iter)


class TestPreparePipelineState:

    def test_prepare_pipeline_state_valid_diff(self):
        state = prepare_pipeline_state(SAMPLE_DIFF, "TEST01")
        assert state.diff_text == SAMPLE_DIFF
        assert state.pr_number == "TEST01"
        assert state.module_name == "module_TEST01"
        assert len(state.function_signatures) > 0

    def test_prepare_pipeline_state_invalid_diff(self):
        with pytest.raises(ValueError):
            prepare_pipeline_state("", "TEST01")


class TestGenerateTestcasesMarkdown:

    def test_generate_testcases_markdown(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        md = generate_testcases_markdown(tc_file, state)

        assert "# Test Cases — PR #TEST01" in md
        assert "## Function Overview" in md
        assert "## Test Cases" in md
        assert "## Engineer Review Checklist" in md
        assert "S001" in md
        assert "30u" in md
        assert "add_values" in md

    def test_generate_testcases_markdown_includes_struct_fields(self):
        tc_file = TestCaseFile(
            pr_number="TEST02",
            module_name="module_TEST02",
            generated_at="2026-01-01T00:00:00+00:00",
            functions={"process_act": FunctionMeta(signature="void process_act(Actuator_t act)", return_type="void", description="Process actuator")},
            test_cases=[
                TestCase(
                    scenario_id="S001",
                    function_name="process_act",
                    scenario="Normal actuator",
                    test_type=TestType.NORMAL,
                    inputs={"act": {"field_a": "10u", "field_b": "FALSE"}},
                    expected_return="E_OK",
                )
            ],
        )
        state = _make_state_with_all_outputs()
        md = generate_testcases_markdown(tc_file, state)

        assert "field_a: 10u" in md
        assert "field_b: FALSE" in md

    def test_generate_testcases_markdown_includes_hal_stubs(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        tc_file.hal_stubs = ["HAL_ADC_Read", "HAL_GPIO_Write"]
        md = generate_testcases_markdown(tc_file, state)
        assert "## HAL Stubs Required" in md
        assert "HAL_ADC_Read" in md
        assert "HAL_GPIO_Write" in md

    def test_generate_testcases_markdown_includes_self_review(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        md = generate_testcases_markdown(tc_file, state)
        assert "## AI Self-Review Notes" in md
        assert "Scenarios planned" in md

    def test_generate_testcases_markdown_checklist_items(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        md = generate_testcases_markdown(tc_file, state)
        assert "- [ ] Struct field names correct" in md
        assert "- [ ] Boundary values match hardware constraints" in md
        assert "- [ ] HAL stubs correctly identified" in md
        assert "- [ ] Expected returns correct" in md
        assert "- [ ] MC/DC coverage adequate" in md


class TestWriteOutputs:

    def test_write_outputs_creates_files(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        md = generate_testcases_markdown(tc_file, state)
        written = write_outputs(tc_file, md, "TEST01")

        assert os.path.exists(written["testcases_md"])
        assert os.path.exists(written["testcases_json"])
        assert "pr_TEST01_testcases.md" in written["testcases_md"]
        assert "pr_TEST01_testcases.json" in written["testcases_json"]

    def test_write_outputs_creates_human_review(self):
        tc_file = TestCaseFile(
            pr_number="TEST03",
            module_name="module_TEST03",
            generated_at="2026-01-01T00:00:00+00:00",
            functions={"f": FunctionMeta(signature="void f(void)", return_type="void", description="test")},
            test_cases=[
                TestCase(
                    scenario_id="S001",
                    function_name="f",
                    scenario="HW test",
                    test_type=TestType.FAULT_INJECTION,
                    inputs={},
                    expected_return="NEEDS_HUMAN",
                    needs_human_review=True,
                    human_review_reason="Hardware register value unknown",
                )
            ],
        )
        state = _make_state_with_all_outputs()
        md = generate_testcases_markdown(tc_file, state)
        written = write_outputs(tc_file, md, "TEST03")

        assert "human_review_md" in written
        assert os.path.exists(written["human_review_md"])

    def test_write_outputs_json_is_valid(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        md = generate_testcases_markdown(tc_file, state)
        written = write_outputs(tc_file, md, "TEST01")

        with open(written["testcases_json"], "r") as f:
            data = json.loads(f.read())
        assert data["pr_number"] == "TEST01"
        assert len(data["test_cases"]) >= 1


class TestExtractTestcaseFile:

    def test_extract_testcase_file_valid(self):
        state = _make_state_with_all_outputs()
        tc_file = extract_testcase_file(state)
        assert isinstance(tc_file, TestCaseFile)
        assert tc_file.pr_number == "TEST01"
        assert "add_values" in tc_file.functions
        assert len(tc_file.test_cases) >= 1
        errors = tc_file.validate_internal_consistency()
        assert errors == []

    def test_extract_testcase_file_uses_self_review(self):
        corrected = dict(SAMPLE_ASSEMBLED_JSON)
        corrected["test_cases"][0]["expected_return"] = "42u"

        state = PipelineState(
            pr_number="TEST04",
            module_name="module_TEST04",
            function_signatures=[{"name": "add_values"}],
            assembled_json=SAMPLE_ASSEMBLED_JSON,
            self_review_result={**corrected, "self_review": {"issues_found": [], "issues_fixed": []}},
        )
        tc_file = extract_testcase_file(state)
        assert tc_file.test_cases[0].expected_return == "42u"

    def test_extract_testcase_file_handles_string_json(self):
        state = PipelineState(
            pr_number="TEST05",
            module_name="module_TEST05",
            function_signatures=[{"name": "add_values"}],
            assembled_json=json.dumps(SAMPLE_ASSEMBLED_JSON),
            self_review_result=json.dumps(SAMPLE_SELF_REVIEW),
        )
        tc_file = extract_testcase_file(state)
        assert isinstance(tc_file, TestCaseFile)


class TestRunStage1WithValidators:

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    @patch("src.stage1_generator.fill_scenario_gaps")
    def test_run_stage1_with_validators_calls_gap_filler(self, mock_fill, mock_llm):
        mock_fill.side_effect = lambda x, y, z: x
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())
        state = prepare_pipeline_state(SAMPLE_DIFF, "TEST06")
        state = run_stage1_with_validators(state)
        assert mock_fill.call_count >= 1

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    @patch("src.stage1_generator.sanitize_values")
    def test_run_stage1_with_validators_calls_sanitizer(self, mock_sanitize, mock_llm):
        mock_sanitize.side_effect = lambda x, y: x
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())
        state = prepare_pipeline_state(SAMPLE_DIFF, "TEST07")
        state = run_stage1_with_validators(state)
        assert mock_sanitize.call_count >= 1


class TestRunStage1Integration:

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_stage1_full_integration(self, mock_llm):
        mock_llm.side_effect = _ThreadSafeMock(_mock_llm_responses())
        tc_file, state = run_stage1(SAMPLE_DIFF, "TEST08")

        assert isinstance(tc_file, TestCaseFile)
        assert tc_file.pr_number == "TEST08"
        assert "add_values" in tc_file.functions
        assert len(tc_file.test_cases) >= 1

        md_path = os.path.join(GENERATED_TESTS_DIR, "pr_TEST08_testcases.md")
        json_path = os.path.join(GENERATED_TESTS_DIR, "pr_TEST08_testcases.json")
        assert os.path.exists(md_path)
        assert os.path.exists(json_path)
