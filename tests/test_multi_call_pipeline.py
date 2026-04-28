"""
Tests for LLM pipeline orchestration with retry logic.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call

from src.multi_call_pipeline import (
    PipelineState,
    _extract_json,
    _call_llm_focused,
    _validate_stage_output,
)


class TestPipelineState:
    """Test PipelineState dataclass defaults and field assignment"""

    def test_pipeline_state_defaults(self):
        """Verify all fields have correct defaults"""
        state = PipelineState()
        assert state.diff_text == ""
        assert state.pr_number == ""
        assert state.module_name == ""
        assert state.function_signatures == []
        assert state.struct_definitions == {}
        assert state.typedef_map == {}
        assert state.macro_constants == {}
        assert state.hal_functions == []
        assert state.code_analysis == ""
        assert state.type_map == {}
        assert state.complexity_tiers == {}
        assert state.scenarios_raw == ""
        assert state.scenarios_critique == ""
        assert state.scenarios_final == ""
        assert state.values_raw == ""
        assert state.values_critique == ""
        assert state.values_final == ""
        assert state.stubs_raw == ""
        assert state.stubs_final == ""
        assert state.assembled_json == ""
        assert state.self_review_result == ""
        assert state.validation_errors == []
        assert state.call_count == 0
        assert state.retry_count == 0

    def test_pipeline_state_field_assignment(self):
        """Verify values persist after assignment"""
        state = PipelineState()
        state.diff_text = "some diff"
        state.function_signatures = [{"name": "foo"}]
        state.type_map = {"x": "int"}
        state.call_count = 5
        assert state.diff_text == "some diff"
        assert state.function_signatures == [{"name": "foo"}]
        assert state.type_map == {"x": "int"}
        assert state.call_count == 5


class TestExtractJson:
    """Test _extract_json helper"""

    def test_extract_json_direct(self):
        """Direct JSON parse"""
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_json_markdown_wrapped(self):
        """JSON inside markdown code block"""
        result = _extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_extract_json_with_surrounding_text(self):
        """JSON embedded in surrounding text"""
        result = _extract_json('Here is the result:\n{"key": "value"}\nDone.')
        assert result == {"key": "value"}

    def test_extract_json_invalid_raises(self):
        """Non-JSON raises JSONDecodeError"""
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")

    def test_extract_json_empty_raises(self):
        """Empty string raises JSONDecodeError"""
        with pytest.raises(json.JSONDecodeError):
            _extract_json("")

    def test_extract_json_nested(self):
        """Nested JSON object"""
        result = _extract_json('{"outer": {"inner": 42}}')
        assert result == {"outer": {"inner": 42}}

    def test_extract_json_markdown_no_lang(self):
        """Markdown code block without language specifier"""
        result = _extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}


class TestCallLlmFocused:
    """Test _call_llm_focused with mocked LLM"""

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_success(self, mock_llm):
        """Successful call returns response"""
        mock_llm.return_value = "This is the LLM response"
        result = _call_llm_focused("system", "user", "test_call")
        assert result == "This is the LLM response"
        mock_llm.assert_called_once()

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_empty_retry(self, mock_llm):
        """Empty response triggers retry, then succeeds"""
        mock_llm.side_effect = ["", "valid response"]
        result = _call_llm_focused("system", "user", "test_empty_retry")
        assert result == "valid response"
        assert mock_llm.call_count == 2

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_empty_all_retries_fail(self, mock_llm):
        """All retries exhausted on empty response raises RuntimeError"""
        mock_llm.return_value = ""
        with pytest.raises(RuntimeError, match="test_empty_fail"):
            _call_llm_focused("system", "user", "test_empty_fail", max_retries=2)
        assert mock_llm.call_count == 3  # max_retries + 1

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_json_parse_retry(self, mock_llm):
        """JSON parse error triggers retry with corrective message, then succeeds"""
        mock_llm.side_effect = ["not json at all", '{"valid": true}']
        result = _call_llm_focused("system", "user", "test_json_retry", expect_json=True)
        assert result == {"valid": True}
        assert mock_llm.call_count == 2

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_json_parse_all_fail(self, mock_llm):
        """All retries on JSON parse failure raises RuntimeError"""
        mock_llm.return_value = "not json at all"
        with pytest.raises(RuntimeError, match="test_json_fail"):
            _call_llm_focused("system", "user", "test_json_fail", expect_json=True, max_retries=1)
        assert mock_llm.call_count == 2

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_expect_json_false(self, mock_llm):
        """expect_json=False returns raw string without parsing"""
        mock_llm.return_value = "This is plain text, not JSON"
        result = _call_llm_focused("system", "user", "test_plain", expect_json=False)
        assert result == "This is plain text, not JSON"

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_json_markdown_wrapped(self, mock_llm):
        """JSON in markdown code block is extracted"""
        mock_llm.return_value = '```json\n{"parsed": "from_md"}\n```'
        result = _call_llm_focused("system", "user", "test_md_json", expect_json=True)
        assert result == {"parsed": "from_md"}

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_call_llm_focused_exception_retry(self, mock_llm):
        """LLM exception triggers retry"""
        mock_llm.side_effect = [Exception("timeout"), "recovered"]
        result = _call_llm_focused("system", "user", "test_exc_retry", max_retries=2)
        assert result == "recovered"
        assert mock_llm.call_count == 2


class TestValidateStageOutput:
    """Test _validate_stage_output helper"""

    def test_validate_stage_output_all_present(self):
        """All required fields populated returns empty error list"""
        state = PipelineState()
        state.diff_text = "some diff"
        state.function_signatures = [{"name": "foo"}]
        errors = _validate_stage_output(state, "test", ["diff_text", "function_signatures"])
        assert errors == []

    def test_validate_stage_output_missing_field(self):
        """Empty required field generates error"""
        state = PipelineState()
        state.diff_text = "some diff"
        # function_signatures is empty list by default
        errors = _validate_stage_output(state, "test", ["diff_text", "function_signatures"])
        assert len(errors) == 1
        assert "function_signatures" in errors[0]

    def test_validate_stage_output_multiple_missing(self):
        """Multiple empty fields all listed in errors"""
        state = PipelineState()
        errors = _validate_stage_output(state, "test", ["diff_text", "type_map", "code_analysis"])
        assert len(errors) == 3

    def test_validate_stage_output_empty_string(self):
        """Empty string counts as missing"""
        state = PipelineState()
        state.diff_text = ""
        errors = _validate_stage_output(state, "test", ["diff_text"])
        assert len(errors) == 1

    def test_validate_stage_output_empty_dict(self):
        """Empty dict counts as missing"""
        state = PipelineState()
        state.type_map = {}
        errors = _validate_stage_output(state, "test", ["type_map"])
        assert len(errors) == 1

    def test_validate_stage_output_populated_dict(self):
        """Non-empty dict is valid"""
        state = PipelineState()
        state.type_map = {"x": "int"}
        errors = _validate_stage_output(state, "test", ["type_map"])
        assert errors == []


# ---------------------------------------------------------------------------
# Task 2: Orchestration tests
# ---------------------------------------------------------------------------

from src.multi_call_pipeline import (
    SYSTEM_PROMPT_1A,
    SYSTEM_PROMPT_1B,
    SYSTEM_PROMPT_1C,
    SYSTEM_PROMPT_2A,
    SYSTEM_PROMPT_2B,
    SYSTEM_PROMPT_2C,
    SYSTEM_PROMPT_3A,
    SYSTEM_PROMPT_3B,
    SYSTEM_PROMPT_3C,
    SYSTEM_PROMPT_4A,
    SYSTEM_PROMPT_4B,
    SYSTEM_PROMPT_5A,
    SYSTEM_PROMPT_5B,
    _build_1a_user_prompt,
    _build_1b_user_prompt,
    _build_1c_user_prompt,
    _build_2a_user_prompt,
    _build_2b_user_prompt,
    _build_2c_user_prompt,
    _build_3a_user_prompt,
    _build_3b_user_prompt,
    _build_3c_user_prompt,
    _build_4a_user_prompt,
    _build_4b_user_prompt,
    _build_5a_user_prompt,
    _build_5b_user_prompt,
    _run_stage_1_parallel,
    _run_stage_sequential,
    run_multi_call_pipeline,
)


def _make_state():
    """Create a state with pre-populated input fields."""
    return PipelineState(
        diff_text="int add(int a, int b) { return a + b; }",
        pr_number="PR001",
        module_name="math",
        function_signatures=[{"name": "add", "return_type": "int", "parameters": []}],
        struct_definitions={"Point": ["x", "y"]},
        typedef_map={"MyType": "uint8_t"},
        hal_functions=["HAL_Read"],
    )


class TestStage1Parallel:
    """Test _run_stage_1_parallel"""

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_stage_1_parallel_success(self, mock_llm):
        """All 3 parallel calls succeed"""
        responses = iter([
            "Code analysis result",
            '{"type_map": {"a": "int"}}',
            '{"tiers": {"add": "TIER_1"}}',
        ])
        mock_llm.side_effect = lambda p: next(responses)

        state = _make_state()
        state = _run_stage_1_parallel(state)

        assert state.code_analysis == "Code analysis result"
        assert state.type_map == {"type_map": {"a": "int"}}
        assert state.complexity_tiers == {"tiers": {"add": "TIER_1"}}
        assert state.call_count == 3

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_stage_1_parallel_one_fails(self, mock_llm):
        """One call failing raises RuntimeError"""
        responses = iter([
            "ok",
            Exception("LLM error"),
            "ok",
        ])
        mock_llm.side_effect = lambda p: next(responses)

        state = _make_state()
        with pytest.raises(RuntimeError, match="Stage 1"):
            _run_stage_1_parallel(state)


class TestStageSequential:
    """Test _run_stage_sequential"""

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_stage_sequential_success(self, mock_llm):
        """Single sequential call succeeds"""
        mock_llm.return_value = "test response"
        state = _make_state()
        state = _run_stage_sequential(
            state, "2A_test", "sys prompt",
            lambda s: "user prompt", "scenarios_raw", expect_json=False
        )
        assert state.scenarios_raw == "test response"
        assert state.call_count == 1


class TestRunMultiCallPipeline:
    """Test full pipeline orchestration"""

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_multi_call_pipeline_full(self, mock_llm):
        """Full 13-call pipeline completes successfully"""
        responses = iter([
            # Stage 1 (parallel)
            "code analysis output",
            '{"types": {}}',
            '{"tiers": {}}',
            # Stage 2 (sequential)
            "scenarios raw output",
            "scenarios critique output",
            "scenarios final output",
            # Stage 3
            "values raw output",
            "values critique output",
            "values final output",
            # Stage 4
            "stubs raw output",
            "stubs final output",
            # Stage 5
            '{"assembled": true}',
            "self review result",
        ])
        mock_llm.side_effect = lambda p: next(responses)

        state = _make_state()
        state = run_multi_call_pipeline(state)

        assert state.call_count == 13
        assert state.code_analysis == "code analysis output"
        assert state.scenarios_final == "scenarios final output"
        assert state.values_final == "values final output"
        assert state.stubs_final == "stubs final output"
        assert state.assembled_json == {"assembled": True}
        assert state.self_review_result == "self review result"

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_multi_call_pipeline_preflight_fails(self, mock_llm):
        """Empty diff_text fails pre-flight validation"""
        state = PipelineState()
        with pytest.raises(RuntimeError, match="pre-flight"):
            run_multi_call_pipeline(state)

    @patch("src.multi_call_pipeline.call_glm_4_7_flash")
    def test_run_multi_call_pipeline_stage1_fails(self, mock_llm):
        """Stage 1 failure raises RuntimeError"""
        mock_llm.return_value = ""
        state = _make_state()
        with pytest.raises(RuntimeError):
            run_multi_call_pipeline(state)


class TestUserPromptBuilders:
    """Test all 13 user prompt builder functions"""

    def _state_with_all(self):
        state = _make_state()
        state.code_analysis = "analysis text"
        state.type_map = {"a": "int"}
        state.complexity_tiers = {"add": "TIER_1"}
        state.scenarios_raw = "scenarios raw"
        state.scenarios_critique = "critique"
        state.scenarios_final = "final scenarios"
        state.values_raw = "values raw"
        state.values_critique = "value critique"
        state.values_final = "final values"
        state.stubs_raw = "stubs raw"
        state.stubs_final = "final stubs"
        state.assembled_json = {"test": True}
        return state

    def test_build_1a_contains_diff(self):
        s = self._state_with_all()
        result = _build_1a_user_prompt(s)
        assert s.diff_text in result

    def test_build_1a_contains_signatures(self):
        s = self._state_with_all()
        result = _build_1a_user_prompt(s)
        assert "add" in result

    def test_build_1b_contains_signatures(self):
        s = self._state_with_all()
        result = _build_1b_user_prompt(s)
        assert "add" in result

    def test_build_1b_contains_structs(self):
        s = self._state_with_all()
        result = _build_1b_user_prompt(s)
        assert "Point" in result

    def test_build_1b_contains_typedefs(self):
        s = self._state_with_all()
        result = _build_1b_user_prompt(s)
        assert "MyType" in result

    def test_build_1c_contains_signatures(self):
        s = self._state_with_all()
        result = _build_1c_user_prompt(s)
        assert "add" in result

    def test_build_2a_contains_analysis(self):
        s = self._state_with_all()
        result = _build_2a_user_prompt(s)
        assert "analysis text" in result

    def test_build_2a_contains_type_map(self):
        s = self._state_with_all()
        result = _build_2a_user_prompt(s)
        assert "type_map" in result.lower() or "int" in result

    def test_build_2b_contains_scenarios(self):
        s = self._state_with_all()
        result = _build_2b_user_prompt(s)
        assert "scenarios raw" in result

    def test_build_2c_contains_critique(self):
        s = self._state_with_all()
        result = _build_2c_user_prompt(s)
        assert "critique" in result

    def test_build_3a_contains_scenarios_final(self):
        s = self._state_with_all()
        result = _build_3a_user_prompt(s)
        assert "final scenarios" in result

    def test_build_3b_contains_values(self):
        s = self._state_with_all()
        result = _build_3b_user_prompt(s)
        assert "values raw" in result

    def test_build_3c_contains_critique(self):
        s = self._state_with_all()
        result = _build_3c_user_prompt(s)
        assert "value critique" in result

    def test_build_4a_contains_hal(self):
        s = self._state_with_all()
        result = _build_4a_user_prompt(s)
        assert "HAL_Read" in result

    def test_build_4b_contains_stubs(self):
        s = self._state_with_all()
        result = _build_4b_user_prompt(s)
        assert "stubs raw" in result

    def test_build_5a_contains_all(self):
        s = self._state_with_all()
        result = _build_5a_user_prompt(s)
        assert "final scenarios" in result
        assert "final values" in result
        assert "final stubs" in result

    def test_build_5b_contains_json(self):
        s = self._state_with_all()
        result = _build_5b_user_prompt(s)
        assert "test" in result


class TestSystemPrompts:
    """Verify all 13 system prompt constants exist"""

    def test_all_13_prompts_exist(self):
        prompts = [
            SYSTEM_PROMPT_1A, SYSTEM_PROMPT_1B, SYSTEM_PROMPT_1C,
            SYSTEM_PROMPT_2A, SYSTEM_PROMPT_2B, SYSTEM_PROMPT_2C,
            SYSTEM_PROMPT_3A, SYSTEM_PROMPT_3B, SYSTEM_PROMPT_3C,
            SYSTEM_PROMPT_4A, SYSTEM_PROMPT_4B,
            SYSTEM_PROMPT_5A, SYSTEM_PROMPT_5B,
        ]
        assert len(prompts) == 13
        for p in prompts:
            assert isinstance(p, str)
            assert len(p) > 0
