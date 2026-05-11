"""
Stage 1 Generator — 13-LLM call pipeline for intelligent test case design.

Orchestrates all 13 calls with deterministic validators between stages.
Produces testcases.md (human-readable) and testcases.json (machine-readable).
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.context_assembler import extract_context_from_diff, ContextPackage
from src.diff_validator import validate_diff
from src.multi_call_pipeline import (
    PipelineState,
    _validate_stage_output,
    _run_stage_1_parallel,
    _run_stage_sequential,
    SYSTEM_PROMPT_1A, SYSTEM_PROMPT_1B, SYSTEM_PROMPT_1C,
    SYSTEM_PROMPT_2A, SYSTEM_PROMPT_2B, SYSTEM_PROMPT_2C,
    SYSTEM_PROMPT_3A, SYSTEM_PROMPT_3B, SYSTEM_PROMPT_3C,
    SYSTEM_PROMPT_4A, SYSTEM_PROMPT_4B,
    SYSTEM_PROMPT_5A, SYSTEM_PROMPT_5B,
    _build_2a_user_prompt, _build_2b_user_prompt, _build_2c_user_prompt,
    _build_3a_user_prompt, _build_3b_user_prompt, _build_3c_user_prompt,
    _build_4a_user_prompt, _build_4b_user_prompt,
    _build_5a_user_prompt, _build_5b_user_prompt,
)
from src.schemas import TestCaseFile, TestCase, FunctionMeta, StubConfig, TestType
from src.scenario_validator import fill_gaps as fill_scenario_gaps, validate_scenarios
from src.value_sanitizer import sanitize_values

logger = logging.getLogger(__name__)

GENERATED_TESTS_DIR = "generated_tests"


def prepare_pipeline_state(diff_text: str, pr_number: str) -> PipelineState:
    """
    Validate diff and extract context into a PipelineState.

    Args:
        diff_text: Raw unified diff content
        pr_number: PR identifier

    Returns:
        Populated PipelineState ready for the pipeline

    Raises:
        ValueError: If diff is invalid
    """
    is_valid, error_msg = validate_diff(diff_text)
    if not is_valid:
        raise ValueError(f"Invalid diff: {error_msg}")

    context = extract_context_from_diff(diff_text)

    state = PipelineState(
        diff_text=context.diff_text,
        pr_number=pr_number,
        module_name=f"module_{pr_number}",
        function_signatures=context.function_signatures,
        struct_definitions=context.struct_definitions,
        typedef_map=context.typedef_map,
        macro_constants=context.macro_constants,
        hal_functions=list(context.hal_functions),
    )
    return state


def run_stage1_with_validators(state: PipelineState) -> PipelineState:
    """
    Run the full 13-call pipeline with deterministic validators wired between stages.

    Stage flow:
    1. Pre-flight: validate diff and context
    2. Stage 1 (parallel): 1A, 1B, 1C
    3. Stage 2 (sequential): 2A -> [gap fill] -> 2B -> 2C -> [validate]
    4. Stage 3 (sequential): 3A -> [sanitize] -> 3B -> 3C
    5. Stage 4 (sequential): 4A -> 4B
    6. Stage 5 (sequential): 5A -> 5B

    Args:
        state: Populated PipelineState from prepare_pipeline_state

    Returns:
        PipelineState with all 13 call outputs populated

    Raises:
        RuntimeError: If pre-flight or stage validation fails
    """
    pre_errors = _validate_stage_output(state, "pre-flight", ["diff_text", "function_signatures"])
    if pre_errors:
        raise RuntimeError(f"Pipeline pre-flight validation failed: {pre_errors}")

    state = _run_stage_1_parallel(state)
    stage1_errors = _validate_stage_output(state, "1", ["code_analysis", "type_map", "complexity_tiers"])
    if stage1_errors:
        state.validation_errors.extend(stage1_errors)
        raise RuntimeError(f"Stage 1 validation failed: {stage1_errors}")

    state = _run_stage_sequential(state, "2A_Scenario_Planner", SYSTEM_PROMPT_2A, _build_2a_user_prompt, "scenarios_raw", expect_json=True)
    state.scenarios_raw = fill_scenario_gaps(state.scenarios_raw, state.type_map, state.function_signatures)
    state = _run_stage_sequential(state, "2B_Scenario_Critic", SYSTEM_PROMPT_2B, _build_2b_user_prompt, "scenarios_critique", expect_json=True)
    state = _run_stage_sequential(state, "2C_Scenario_Finalizer", SYSTEM_PROMPT_2C, _build_2c_user_prompt, "scenarios_final", expect_json=True)
    scenario_errors = validate_scenarios(state.scenarios_final)
    if scenario_errors:
        logger.warning("Scenario validation warnings: %s", scenario_errors)

    state = _run_stage_sequential(state, "3A_Value_Generator", SYSTEM_PROMPT_3A, _build_3a_user_prompt, "values_raw", expect_json=True)
    state.values_raw = sanitize_values(state.values_raw, state.type_map)
    state = _run_stage_sequential(state, "3B_Value_Critic", SYSTEM_PROMPT_3B, _build_3b_user_prompt, "values_critique", expect_json=True)
    state = _run_stage_sequential(state, "3C_Value_Finalizer", SYSTEM_PROMPT_3C, _build_3c_user_prompt, "values_final", expect_json=True)

    state = _run_stage_sequential(state, "4A_Stub_Analyst", SYSTEM_PROMPT_4A, _build_4a_user_prompt, "stubs_raw", expect_json=True)
    state = _run_stage_sequential(state, "4B_Stub_Critic", SYSTEM_PROMPT_4B, _build_4b_user_prompt, "stubs_final", expect_json=True)

    state = _run_stage_sequential(state, "5A_JSON_Assembler", SYSTEM_PROMPT_5A, _build_5a_user_prompt, "assembled_json", expect_json=True)
    state = _run_stage_sequential(state, "5B_Self_Review", SYSTEM_PROMPT_5B, _build_5b_user_prompt, "self_review_result", expect_json=True)

    return state


def _parse_json_field(value: Any) -> Any:
    """Parse a field that may be a dict or JSON string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def extract_testcase_file(state: PipelineState) -> TestCaseFile:
    """
    Extract and validate a TestCaseFile from pipeline outputs.

    Uses self_review_result if it contains a corrected JSON,
    otherwise falls back to assembled_json.

    Args:
        state: PipelineState with assembled_json and self_review_result populated

    Returns:
        Validated TestCaseFile

    Raises:
        ValueError: If the extracted data cannot form a valid TestCaseFile
    """
    assembled = _parse_json_field(state.assembled_json)
    review = _parse_json_field(state.self_review_result)

    data = review if review and "test_cases" in review else assembled
    if not data or "test_cases" not in data:
        data = assembled

    functions = {}
    for name, meta in data.get("functions", {}).items():
        functions[name] = FunctionMeta(**meta)

    test_cases = []
    for tc_data in data.get("test_cases", []):
        stubs = {}
        for sname, sconfig in tc_data.get("stubs", {}).items():
            stubs[sname] = StubConfig(**sconfig)
        tc_data_copy = {k: v for k, v in tc_data.items() if k != "stubs"}
        tc_data_copy["stubs"] = stubs
        inputs = tc_data_copy.get("inputs", {})
        for k, v in inputs.items():
            if not isinstance(v, (str, dict)):
                inputs[k] = str(v)
        tc_data_copy["inputs"] = inputs
        if "expected_return" in tc_data_copy and not isinstance(tc_data_copy["expected_return"], str):
            tc_data_copy["expected_return"] = str(tc_data_copy["expected_return"])
        test_cases.append(TestCase(**tc_data_copy))

    tc_file = TestCaseFile(
        version=data.get("version", "1.0"),
        pr_number=state.pr_number,
        module_name=state.module_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        functions=functions,
        test_cases=test_cases,
        hal_stubs=data.get("hal_stubs", []),
    )

    consistency_errors = tc_file.validate_internal_consistency()
    if consistency_errors:
        for err in consistency_errors:
            logger.warning("Consistency error: %s", err)

    return tc_file


def generate_testcases_markdown(tc_file: TestCaseFile, state: PipelineState) -> str:
    """
    Generate human-readable testcases.md for engineer review.

    Args:
        tc_file: Validated TestCaseFile
        state: PipelineState with intermediate outputs for context

    Returns:
        Complete markdown string
    """
    lines = []
    lines.append(f"# Test Cases — PR #{tc_file.pr_number}")
    lines.append("")
    lines.append(f"**Module:** {tc_file.module_name}")
    lines.append(f"**Generated:** {tc_file.generated_at}")
    lines.append(f"**Functions:** {len(tc_file.functions)}")
    lines.append(f"**Test Cases:** {len(tc_file.test_cases)}")
    lines.append(f"**HAL Stubs:** {len(tc_file.hal_stubs)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Function Overview")
    lines.append("")
    for func_name, meta in tc_file.functions.items():
        lines.append(f"### {func_name}")
        lines.append(f"- **Signature:** `{meta.signature}`")
        lines.append(f"- **Returns:** `{meta.return_type}`")
        lines.append(f"- **Description:** {meta.description}")
        lines.append(f"- **ASIL Level:** {meta.asil_level}")
        lines.append("")

    if tc_file.hal_stubs:
        lines.append("## HAL Stubs Required")
        lines.append("")
        for stub_name in tc_file.hal_stubs:
            lines.append(f"- `{stub_name}`")
        lines.append("")

    if state.code_analysis:
        lines.append("## Code Analysis")
        lines.append("")
        lines.append(state.code_analysis)
        lines.append("")

    lines.append("## Test Cases")
    lines.append("")
    for func_name in tc_file.functions:
        func_tests = [tc for tc in tc_file.test_cases if tc.function_name == func_name]
        if not func_tests:
            continue
        lines.append(f"### {func_name} ({len(func_tests)} tests)")
        lines.append("")
        lines.append("| ID | Scenario | Type | Expected Return |")
        lines.append("|----|----------|------|-----------------|")
        for tc in func_tests:
            lines.append(f"| {tc.scenario_id} | {tc.scenario} | {tc.test_type.value} | `{tc.expected_return}` |")
        lines.append("")
        for tc in func_tests:
            lines.append(f"#### {tc.scenario_id}: {tc.scenario}")
            lines.append(f"**Type:** {tc.test_type.value}")
            lines.append(f"**Intent:** {tc.scenario}")
            lines.append("")
            lines.append("**Inputs:**")
            for param_name, value in tc.inputs.items():
                if isinstance(value, dict):
                    lines.append(f"- `{param_name}:`")
                    for field_name, field_value in value.items():
                        lines.append(f"  - `{field_name}: {field_value}`")
                else:
                    lines.append(f"- `{param_name}: {value}`")
            lines.append("")
            lines.append(f"**Expected Return:** `{tc.expected_return}`")
            if tc.expected_output_params:
                lines.append("**Output Params:**")
                for pname, pval in tc.expected_output_params.items():
                    lines.append(f"- `{pname}: {pval}`")
            if tc.stubs:
                lines.append("**Stubs:**")
                for sname, sconfig in tc.stubs.items():
                    lines.append(f"- `{sname}`: return `{sconfig.return_value}`, calls={sconfig.expected_call_count}")
            if tc.needs_human_review:
                lines.append(f"**\\u26a0 NEEDS HUMAN REVIEW:** {tc.human_review_reason or 'Hardware-dependent values'}")
            lines.append("")

    if state.self_review_result:
        lines.append("## AI Self-Review Notes")
        lines.append("")
        review = _parse_json_field(state.self_review_result)
        if "self_review" in review:
            sr = review["self_review"]
            lines.append(f"- Scenarios planned: {sr.get('scenarios_planned', 'N/A')}")
            lines.append(f"- Test cases generated: {sr.get('test_cases_generated', 'N/A')}")
            for issue in sr.get("issues_found", []):
                lines.append(f"- Found: {issue}")
            for fix in sr.get("issues_fixed", []):
                lines.append(f"- Fixed: {fix}")
        else:
            lines.append(str(state.self_review_result))
        lines.append("")

    lines.append("## Engineer Review Checklist")
    lines.append("")
    lines.append("- [ ] Struct field names correct")
    lines.append("- [ ] Boundary values match hardware constraints")
    lines.append("- [ ] HAL stubs correctly identified")
    lines.append("- [ ] Expected returns correct")
    lines.append("- [ ] MC/DC coverage adequate")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"Edit `pr_{tc_file.pr_number}_testcases.json` if corrections needed.")
    lines.append(f"Re-run: `python run.py --stage2-only pr_{tc_file.pr_number}_testcases.json`")

    return "\n".join(lines)


def write_outputs(tc_file: TestCaseFile, markdown: str, pr_number: str) -> Dict[str, str]:
    """
    Write testcases.md, testcases.json, and optionally human_review.md.

    Args:
        tc_file: Validated TestCaseFile
        markdown: Generated markdown content
        pr_number: PR identifier for file naming

    Returns:
        Dict mapping file description to file path
    """
    os.makedirs(GENERATED_TESTS_DIR, exist_ok=True)

    md_path = os.path.join(GENERATED_TESTS_DIR, f"pr_{pr_number}_testcases.md")
    json_path = os.path.join(GENERATED_TESTS_DIR, f"pr_{pr_number}_testcases.json")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(tc_file.model_dump_json(indent=2))

    written = {
        "testcases_md": md_path,
        "testcases_json": json_path,
    }

    human_review_cases = [tc for tc in tc_file.test_cases if tc.needs_human_review]
    if human_review_cases:
        hr_path = os.path.join(GENERATED_TESTS_DIR, f"human_review_{pr_number}.md")
        hr_lines = [f"# Human Review Required — PR #{pr_number}", ""]
        for tc in human_review_cases:
            hr_lines.append(f"## {tc.scenario_id}: {tc.scenario}")
            hr_lines.append(f"- **Function:** {tc.function_name}")
            hr_lines.append(f"- **Reason:** {tc.human_review_reason or 'Hardware-dependent values'}")
            hr_lines.append(f"- **Expected Return:** `{tc.expected_return}`")
            hr_lines.append("")
        with open(hr_path, "w", encoding="utf-8") as f:
            f.write("\n".join(hr_lines))
        written["human_review_md"] = hr_path

    return written


def run_stage1(diff_text: str, pr_number: str) -> Tuple[TestCaseFile, PipelineState]:
    """
    Main entry point for Stage 1 pipeline.

    Args:
        diff_text: Raw unified diff content
        pr_number: PR identifier

    Returns:
        Tuple of (validated TestCaseFile, PipelineState with all intermediate outputs)

    Raises:
        ValueError: If diff is invalid
        RuntimeError: If pipeline fails
    """
    state = prepare_pipeline_state(diff_text, pr_number)
    state = run_stage1_with_validators(state)
    tc_file = extract_testcase_file(state)
    markdown = generate_testcases_markdown(tc_file, state)
    write_outputs(tc_file, markdown, pr_number)
    return tc_file, state
