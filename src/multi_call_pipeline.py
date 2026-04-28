"""
LLM pipeline orchestration with retry logic and parallel execution.

Implements the 13-call pipeline backbone: PipelineState dataclass,
single-call retry wrapper, parallel Stage 1 execution, sequential Stages 2-5,
and stage-level validation hooks.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from glm_client import call_glm_4_7_flash

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """Stores all intermediate outputs for the 13-call LLM pipeline."""

    # Input
    diff_text: str = ""
    pr_number: str = ""
    module_name: str = ""

    # Context (from Phase 1 context_assembler)
    function_signatures: List[Dict] = field(default_factory=list)
    struct_definitions: Dict = field(default_factory=dict)
    typedef_map: Dict[str, str] = field(default_factory=dict)
    macro_constants: Dict[str, str] = field(default_factory=dict)
    hal_functions: List[str] = field(default_factory=list)

    # Stage 1 (parallel)
    code_analysis: str = ""
    type_map: Dict = field(default_factory=dict)
    complexity_tiers: Dict = field(default_factory=dict)

    # Stage 2 (sequential)
    scenarios_raw: str = ""
    scenarios_critique: str = ""
    scenarios_final: str = ""

    # Stage 3 (sequential)
    values_raw: str = ""
    values_critique: str = ""
    values_final: str = ""

    # Stage 4 (sequential)
    stubs_raw: str = ""
    stubs_final: str = ""

    # Stage 5 (sequential)
    assembled_json: str = ""
    self_review_result: str = ""

    # Validation
    validation_errors: List[str] = field(default_factory=list)

    # Metadata
    call_count: int = 0
    retry_count: int = 0


def _extract_json(raw_response: str) -> dict:
    """
    Extract JSON from a raw LLM response string.

    Tries three strategies:
    1. Direct json.loads()
    2. Extract from markdown code block (```json ... ```)
    3. Find first { to last } and parse that substring

    Args:
        raw_response: Raw LLM response text

    Returns:
        Parsed dict

    Raises:
        json.JSONDecodeError: If all extraction attempts fail
    """
    if not raw_response or not raw_response.strip():
        raise json.JSONDecodeError("Empty response", raw_response, 0)

    # Strategy 1: Direct parse
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code block
    md_pattern = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL)
    md_match = md_pattern.search(raw_response)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find first { to last }
    first_brace = raw_response.find('{')
    last_brace = raw_response.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(raw_response[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError(
        f"Could not extract valid JSON from response (length={len(raw_response)})",
        raw_response, 0
    )


def _call_llm_focused(
    system_prompt: str,
    user_prompt: str,
    call_name: str,
    max_retries: int = 2,
    expect_json: bool = False
) -> Union[str, dict]:
    """
    Execute a single LLM call with retry logic.

    Retries on:
    - Empty/whitespace-only responses
    - JSON parse errors (when expect_json=True)

    Args:
        system_prompt: System instructions for the LLM
        user_prompt: User content for the LLM
        call_name: Identifier for logging (e.g., "1A_Code_Analyst")
        max_retries: Maximum number of retries (default 2)
        expect_json: If True, attempt to parse response as JSON

    Returns:
        Raw response string (expect_json=False) or parsed dict (expect_json=True)

    Raises:
        RuntimeError: If all retries are exhausted
    """
    combined_prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nUSER CONTENT:\n{user_prompt}"

    last_error = None
    total_attempts = max_retries + 1

    for attempt in range(total_attempts):
        try:
            response = call_glm_4_7_flash(combined_prompt)

            # Empty response retry
            if not response or not response.strip():
                logger.warning("[%s] Attempt %d/%d: Empty response, retrying",
                               call_name, attempt + 1, total_attempts)
                last_error = "Empty response"
                continue

            # JSON parse retry
            if expect_json:
                try:
                    parsed = _extract_json(response)
                    return parsed
                except json.JSONDecodeError as e:
                    logger.warning("[%s] Attempt %d/%d: JSON parse failed (%s), retrying",
                                   call_name, attempt + 1, total_attempts, str(e))
                    last_error = f"JSON parse error: {e}"
                    combined_prompt += "\n\nIMPORTANT: Your previous output was not valid JSON. Output ONLY valid JSON."
                    continue

            return response

        except Exception as e:
            last_error = str(e)
            logger.warning("[%s] Attempt %d/%d: Exception: %s",
                           call_name, attempt + 1, total_attempts, str(e))
            if attempt < max_retries:
                continue

    raise RuntimeError(f"[{call_name}] Failed after {total_attempts} attempts: {last_error}")


def _validate_stage_output(
    state: PipelineState,
    stage: str,
    required_fields: List[str]
) -> List[str]:
    """
    Validate that required pipeline outputs are present.

    Args:
        state: Current pipeline state
        stage: Stage name for error messages
        required_fields: List of field names that must be populated

    Returns:
        List of error messages (empty = valid)
    """
    errors = []
    for field_name in required_fields:
        value = getattr(state, field_name, None)
        if value is None or value == "" or value == {} or value == []:
            errors.append(f"Stage {stage}: Missing required output '{field_name}'")
    return errors


# ---------------------------------------------------------------------------
# Placeholder system prompts (Phase 3 will replace with real prompts)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_1A = "PLACEHOLDER: Code Analyst — describe what each function does"
SYSTEM_PROMPT_1B = "PLACEHOLDER: Type Inspector — build complete JSON type map"
SYSTEM_PROMPT_1C = "PLACEHOLDER: Complexity Judge — classify each function as TIER_1/2/3"
SYSTEM_PROMPT_2A = "PLACEHOLDER: MC/DC Scenario Planner — plan test scenarios by intent"
SYSTEM_PROMPT_2B = "PLACEHOLDER: Scenario Critic — find gaps in scenario list"
SYSTEM_PROMPT_2C = "PLACEHOLDER: Scenario Finalizer — apply critique fixes"
SYSTEM_PROMPT_3A = "PLACEHOLDER: Concrete Value Generator — assign C values to parameters"
SYSTEM_PROMPT_3B = "PLACEHOLDER: Value Critic — find value errors"
SYSTEM_PROMPT_3C = "PLACEHOLDER: Value Finalizer — apply value fixes"
SYSTEM_PROMPT_4A = "PLACEHOLDER: Stub Analyst — configure Cantata stubs"
SYSTEM_PROMPT_4B = "PLACEHOLDER: Stub Critic — verify stub completeness"
SYSTEM_PROMPT_5A = "PLACEHOLDER: JSON Assembler — merge all stages into TestCaseFile JSON"
SYSTEM_PROMPT_5B = "PLACEHOLDER: Self-Review Auditor — check 12-item checklist"


# ---------------------------------------------------------------------------
# User prompt builder functions
# ---------------------------------------------------------------------------

def _build_1a_user_prompt(state: PipelineState) -> str:
    parts = [f"## Diff Content\n{state.diff_text}"]
    if state.function_signatures:
        parts.append(f"## Function Signatures\n{json.dumps(state.function_signatures, indent=2)}")
    return "\n\n".join(parts)


def _build_1b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.function_signatures:
        parts.append(f"## Function Signatures\n{json.dumps(state.function_signatures, indent=2)}")
    if state.struct_definitions:
        parts.append(f"## Struct Definitions\n{json.dumps(state.struct_definitions, indent=2)}")
    if state.typedef_map:
        parts.append(f"## Typedef Map\n{json.dumps(state.typedef_map, indent=2)}")
    return "\n\n".join(parts)


def _build_1c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.function_signatures:
        parts.append(f"## Function Signatures\n{json.dumps(state.function_signatures, indent=2)}")
    return "\n\n".join(parts)


def _build_2a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.code_analysis:
        parts.append(f"## Code Analysis\n{state.code_analysis}")
    if state.type_map:
        parts.append(f"## Type Map\n{json.dumps(state.type_map, indent=2)}")
    if state.complexity_tiers:
        parts.append(f"## Complexity Tiers\n{json.dumps(state.complexity_tiers, indent=2)}")
    return "\n\n".join(parts)


def _build_2b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_raw:
        parts.append(f"## Scenarios Draft\n{state.scenarios_raw}")
    return "\n\n".join(parts)


def _build_2c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_raw:
        parts.append(f"## Scenarios Draft\n{state.scenarios_raw}")
    if state.scenarios_critique:
        parts.append(f"## Critique\n{state.scenarios_critique}")
    return "\n\n".join(parts)


def _build_3a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_final:
        parts.append(f"## Final Scenarios\n{state.scenarios_final}")
    if state.type_map:
        parts.append(f"## Type Map\n{json.dumps(state.type_map, indent=2)}")
    if state.struct_definitions:
        parts.append(f"## Struct Definitions\n{json.dumps(state.struct_definitions, indent=2)}")
    return "\n\n".join(parts)


def _build_3b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.values_raw:
        parts.append(f"## Values Draft\n{state.values_raw}")
    if state.type_map:
        parts.append(f"## Type Map\n{json.dumps(state.type_map, indent=2)}")
    return "\n\n".join(parts)


def _build_3c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.values_raw:
        parts.append(f"## Values Draft\n{state.values_raw}")
    if state.values_critique:
        parts.append(f"## Value Critique\n{state.values_critique}")
    return "\n\n".join(parts)


def _build_4a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_final:
        parts.append(f"## Final Scenarios\n{state.scenarios_final}")
    if state.hal_functions:
        parts.append(f"## HAL Functions\n{json.dumps(state.hal_functions, indent=2)}")
    return "\n\n".join(parts)


def _build_4b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.stubs_raw:
        parts.append(f"## Stubs Draft\n{state.stubs_raw}")
    if state.hal_functions:
        parts.append(f"## HAL Functions\n{json.dumps(state.hal_functions, indent=2)}")
    return "\n\n".join(parts)


def _build_5a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_final:
        parts.append(f"## Final Scenarios\n{state.scenarios_final}")
    if state.values_final:
        parts.append(f"## Final Values\n{state.values_final}")
    if state.stubs_final:
        parts.append(f"## Final Stubs\n{state.stubs_final}")
    if state.function_signatures:
        parts.append(f"## Function Signatures\n{json.dumps(state.function_signatures, indent=2)}")
    return "\n\n".join(parts)


def _build_5b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.assembled_json:
        if isinstance(state.assembled_json, dict):
            parts.append(f"## Assembled JSON\n{json.dumps(state.assembled_json, indent=2)}")
        else:
            parts.append(f"## Assembled JSON\n{state.assembled_json}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Stage execution functions
# ---------------------------------------------------------------------------

def _run_stage_1_parallel(state: PipelineState) -> PipelineState:
    """Execute Stage 1 calls (1A, 1B, 1C) in parallel via ThreadPoolExecutor."""
    call_specs = {
        "1A_Code_Analyst": {
            "system": SYSTEM_PROMPT_1A,
            "user_builder": _build_1a_user_prompt,
            "expect_json": False,
            "field": "code_analysis",
        },
        "1B_Type_Inspector": {
            "system": SYSTEM_PROMPT_1B,
            "user_builder": _build_1b_user_prompt,
            "expect_json": True,
            "field": "type_map",
        },
        "1C_Complexity_Judge": {
            "system": SYSTEM_PROMPT_1C,
            "user_builder": _build_1c_user_prompt,
            "expect_json": True,
            "field": "complexity_tiers",
        },
    }

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for call_name, spec in call_specs.items():
            user_prompt = spec["user_builder"](state)
            future = executor.submit(
                _call_llm_focused,
                spec["system"],
                user_prompt,
                call_name,
                expect_json=spec["expect_json"],
            )
            futures[future] = (call_name, spec["field"])

        for future in as_completed(futures):
            call_name, state_field = futures[future]
            try:
                result = future.result()
                results[call_name] = (state_field, result)
            except Exception as e:
                for f in futures:
                    f.cancel()
                raise RuntimeError(f"Stage 1 call '{call_name}' failed: {e}")

    for call_name, (state_field, result) in results.items():
        setattr(state, state_field, result)

    state.call_count += 3
    return state


def _run_stage_sequential(
    state: PipelineState,
    call_name: str,
    system_prompt: str,
    user_prompt_builder: Callable,
    state_field: str,
    expect_json: bool = False,
) -> PipelineState:
    """Execute a single sequential stage call."""
    user_prompt = user_prompt_builder(state)
    result = _call_llm_focused(system_prompt, user_prompt, call_name, expect_json=expect_json)
    setattr(state, state_field, result)
    state.call_count += 1
    return state


def run_multi_call_pipeline(state: PipelineState) -> PipelineState:
    """
    Orchestrate all 13 LLM calls through the pipeline.

    Stage 1: Calls 1A, 1B, 1C (parallel via ThreadPoolExecutor)
    Stage 2: Calls 2A, 2B, 2C (sequential, each feeds next)
    Stage 3: Calls 3A, 3B, 3C (sequential)
    Stage 4: Calls 4A, 4B (sequential)
    Stage 5: Calls 5A, 5B (sequential)

    Deterministic validators run between stages.
    """
    # Pre-flight validation
    pre_errors = _validate_stage_output(state, "pre-flight", ["diff_text", "function_signatures"])
    if pre_errors:
        raise RuntimeError(f"Pipeline pre-flight validation failed: {pre_errors}")

    # Stage 1: Parallel (1A, 1B, 1C)
    state = _run_stage_1_parallel(state)
    stage1_errors = _validate_stage_output(state, "1", ["code_analysis", "type_map", "complexity_tiers"])
    if stage1_errors:
        state.validation_errors.extend(stage1_errors)
        raise RuntimeError(f"Stage 1 validation failed: {stage1_errors}")

    # Stage 2: Sequential (2A -> 2B -> 2C)
    state = _run_stage_sequential(state, "2A_Scenario_Planner", SYSTEM_PROMPT_2A, _build_2a_user_prompt, "scenarios_raw", expect_json=False)
    state = _run_stage_sequential(state, "2B_Scenario_Critic", SYSTEM_PROMPT_2B, _build_2b_user_prompt, "scenarios_critique", expect_json=False)
    state = _run_stage_sequential(state, "2C_Scenario_Finalizer", SYSTEM_PROMPT_2C, _build_2c_user_prompt, "scenarios_final", expect_json=False)
    stage2_errors = _validate_stage_output(state, "2", ["scenarios_final"])
    if stage2_errors:
        state.validation_errors.extend(stage2_errors)

    # Stage 3: Sequential (3A -> 3B -> 3C)
    state = _run_stage_sequential(state, "3A_Value_Generator", SYSTEM_PROMPT_3A, _build_3a_user_prompt, "values_raw", expect_json=False)
    state = _run_stage_sequential(state, "3B_Value_Critic", SYSTEM_PROMPT_3B, _build_3b_user_prompt, "values_critique", expect_json=False)
    state = _run_stage_sequential(state, "3C_Value_Finalizer", SYSTEM_PROMPT_3C, _build_3c_user_prompt, "values_final", expect_json=False)
    stage3_errors = _validate_stage_output(state, "3", ["values_final"])
    if stage3_errors:
        state.validation_errors.extend(stage3_errors)

    # Stage 4: Sequential (4A -> 4B)
    state = _run_stage_sequential(state, "4A_Stub_Analyst", SYSTEM_PROMPT_4A, _build_4a_user_prompt, "stubs_raw", expect_json=False)
    state = _run_stage_sequential(state, "4B_Stub_Critic", SYSTEM_PROMPT_4B, _build_4b_user_prompt, "stubs_final", expect_json=False)
    stage4_errors = _validate_stage_output(state, "4", ["stubs_final"])
    if stage4_errors:
        state.validation_errors.extend(stage4_errors)

    # Stage 5: Sequential (5A -> 5B)
    state = _run_stage_sequential(state, "5A_JSON_Assembler", SYSTEM_PROMPT_5A, _build_5a_user_prompt, "assembled_json", expect_json=True)
    state = _run_stage_sequential(state, "5B_Self_Review", SYSTEM_PROMPT_5B, _build_5b_user_prompt, "self_review_result", expect_json=False)

    return state
