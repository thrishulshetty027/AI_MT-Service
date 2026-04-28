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

from src.scenario_validator import fill_gaps as fill_scenario_gaps, validate_scenarios
from src.value_sanitizer import sanitize_values

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

SYSTEM_PROMPT_1A = (
    "You are a C code analyst for safety-critical automotive software.\n"
    "Your ONLY job is to read a C diff and describe in plain English\n"
    "what each changed function does.\n"
    "\n"
    "For each function write:\n"
    "- PURPOSE: What does this function compute, control, or manage?\n"
    "- PARAMETERS: What does each parameter represent in the real world?\n"
    "- LOGIC: Walk through every conditional branch step by step.\n"
    "         For every if/else: what condition triggers each path?\n"
    "         For every switch: what does each case handle?\n"
    "- RETURNS: What does each possible return value mean?\n"
    "- ERRORS: Under what conditions does it return an error?\n"
    "- SIDE EFFECTS: Does it modify any global state or output params?\n"
    "\n"
    "Format: One section per function. Plain English paragraphs.\n"
    "No code. No JSON. No test cases. Just describe the logic clearly.\n"
    "Be specific. Say \"when voltage > 150u the function returns E_NOT_OK\"\n"
    "not \"returns error for invalid input\"."
)

SYSTEM_PROMPT_1B = (
    "You are a C type specialist for automotive AUTOSAR software.\n"
    "Your ONLY job is to build a complete type map from function signatures\n"
    "and struct definitions.\n"
    "\n"
    "Output ONLY this exact JSON structure. No prose. No markdown. No explanation.\n"
    "\n"
    "{\n"
    '  "functions": {\n'
    '    "function_name": {\n'
    '      "return_type": "exact C type string",\n'
    '      "return_meaning": "what the return value represents",\n'
    '      "return_valid_values": ["E_OK", "E_NOT_OK"],\n'
    '      "params": {\n'
    '        "param_name": {\n'
    '          "c_type": "exact C type from signature",\n'
    '          "is_pointer": false,\n'
    '          "is_const": false,\n'
    '          "is_array": false,\n'
    '          "struct_name": null,\n'
    '          "struct_fields": {\n'
    '            "field_name": "field_c_type"\n'
    "          },\n"
    '          "valid_min": "minimum valid value with correct C suffix",\n'
    '          "valid_max": "maximum valid value with correct C suffix",\n'
    '          "null_value": "zero or null representation",\n'
    '          "real_world_meaning": "what this parameter represents"\n'
    "        }\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "}\n"
    "\n"
    "CRITICAL RULES:\n"
    "- struct_fields must contain ONLY fields from the provided struct definitions\n"
    "- Never invent field names\n"
    "- valid_min and valid_max must use correct C suffixes (u for uint, f for float)\n"
    "- null_value for pointers is NULL_PTR, for uint is 0u, for bool is FALSE\n"
    '- If a type is unknown, set c_type to "int" — never leave it empty\n'
)

SYSTEM_PROMPT_1C = (
    "You are a test complexity classifier for automotive C software.\n"
    "Your ONLY job is to classify each function into a testing tier.\n"
    "\n"
    "TIER_1_AUTO: GLM can generate complete tests automatically\n"
    "  - Cyclomatic complexity <= 4\n"
    "  - Parameters <= 3\n"
    "  - No hardware register access\n"
    "  - No OS/RTOS calls\n"
    "  - No function pointers\n"
    "\n"
    "TIER_2_REVIEW: GLM generates tests, human must review MC/DC\n"
    "  - Cyclomatic complexity 5-8\n"
    "  - Parameters 4-6\n"
    "  - Calls 1-2 HAL functions\n"
    "\n"
    "TIER_3_MANUAL: Human writes tests, pipeline provides scaffold only\n"
    "  - Cyclomatic complexity > 8\n"
    "  - Parameters > 6\n"
    "  - Direct hardware register access (volatile, address)\n"
    "  - Multiple OS interactions (GetResource, ReleaseResource)\n"
    "  - Complex callback chains\n"
    "\n"
    "Count one decision point for each:\n"
    "  if, else if, while, for, switch case, &&, ||, ternary ?:\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "classifications": {\n'
    '    "function_name": {\n'
    '      "tier": "TIER_1_AUTO",\n'
    '      "cyclomatic_score": 3,\n'
    '      "param_count": 2,\n'
    '      "hw_coupled": false,\n'
    '      "os_coupled": false,\n'
    '      "reason": "simple arithmetic with one branch"\n'
    "    }\n"
    "  }\n"
    "}\n"
)

SYSTEM_PROMPT_2A = (
    "You are a test scenario planner for ISO 26262 ASIL-B automotive software.\n"
    "Your ONLY job is to plan test scenarios — NOT values, just intent.\n"
    "\n"
    "For each function you MUST generate scenarios for:\n"
    "1. Normal operation with valid typical inputs\n"
    "2. Minimum boundary value for each numeric parameter\n"
    "3. Maximum boundary value for each numeric parameter\n"
    "4. NULL_PTR input for each pointer parameter\n"
    "5. Each branch of every if/else — both true AND false path\n"
    "6. Each case of every switch statement\n"
    "7. Input that triggers error return\n"
    "8. Input that causes overflow or out-of-range behavior\n"
    "\n"
    "THINKING PROCESS — do this step by step before writing output:\n"
    "1. List every conditional in the function\n"
    "2. For each conditional: what makes it true? what makes it false?\n"
    "3. Are there combinations of conditions that create unique paths?\n"
    "4. What is the minimum set of tests for MC/DC on this function?\n"
    "5. Then write the scenario list.\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "function_name": "exact_name",\n'
    '      "scenario_id": "S001",\n'
    '      "scenario_name": "short descriptive name",\n'
    '      "intent": "one sentence: what this test verifies",\n'
    '      "test_type": "normal|boundary_min|boundary_max|null_ptr|negative|overflow|fault_injection",\n'
    '      "branch_targeted": "which conditional branch this covers, or null",\n'
    '      "expected_behavior": "what should happen: return value + side effects"\n'
    "    }\n"
    "  ]\n"
    "}\n"
)

SYSTEM_PROMPT_2B = (
    "You are a test coverage critic for ASIL-B automotive software.\n"
    "Your ONLY job is to identify gaps and problems in a test scenario list.\n"
    "\n"
    "Review the scenarios for these specific issues:\n"
    "1. MISSING BRANCHES: Is every if/else covered both true and false?\n"
    "2. MISSING NULL TESTS: Does every pointer parameter have a null_ptr scenario?\n"
    "3. MISSING BOUNDARIES: Does every numeric param have min and max scenarios?\n"
    "4. MAGIC NUMBERS: Are any values hardcoded that should use project constants?\n"
    "5. REDUNDANT SCENARIOS: Are any two scenarios testing identical paths?\n"
    "6. WRONG EXPECTED: Does the expected_behavior match what the code actually does?\n"
    "7. ASIL GAPS: What would a TUV auditor say is missing?\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "issues": [\n'
    "    {\n"
    '      "type": "MISSING_BRANCH|MISSING_NULL|MISSING_BOUNDARY|REDUNDANT|WRONG_EXPECTED|ASIL_GAP",\n'
    '      "function_name": "name",\n'
    '      "affected_scenario_id": "S002 or null if new scenario needed",\n'
    '      "description": "specific description of the issue",\n'
    '      "fix": "specific fix: add scenario / remove scenario / change value"\n'
    "    }\n"
    "  ],\n"
    '  "scenarios_to_add": [\n'
    "    {\n"
    '      "function_name": "name",\n'
    '      "scenario_id": "S_NEW_001",\n'
    '      "scenario_name": "name",\n'
    '      "intent": "what this tests",\n'
    '      "test_type": "...",\n'
    '      "branch_targeted": "...",\n'
    '      "expected_behavior": "..."\n'
    "    }\n"
    "  ],\n"
    '  "scenario_ids_to_remove": ["S003"]\n'
    "}\n"
)

SYSTEM_PROMPT_2C = (
    "You are a test scenario finalizer for automotive C software.\n"
    "Your ONLY job is to apply all critique fixes and produce the final\n"
    "clean scenario list.\n"
    "\n"
    "Instructions:\n"
    "1. Start with the original scenario list\n"
    "2. Remove every scenario_id in scenarios_to_remove\n"
    "3. Add every scenario in scenarios_to_add\n"
    "4. Fix every issue described in the issues list\n"
    "5. Renumber all scenario_ids sequentially: S001, S002, S003...\n"
    "6. Ensure every scenario has all required fields\n"
    "\n"
    'Output ONLY this JSON (the complete final scenario list):\n'
    "{\n"
    '  "scenarios": [\n'
    "    {\n"
    '      "function_name": "exact_name",\n'
    '      "scenario_id": "S001",\n'
    '      "scenario_name": "short name",\n'
    '      "intent": "what this tests",\n'
    '      "test_type": "normal|boundary_min|boundary_max|null_ptr|negative|overflow|fault_injection",\n'
    '      "branch_targeted": "which branch or null",\n'
    '      "expected_behavior": "expected return + side effects"\n'
    "    }\n"
    "  ],\n"
    '  "coverage_summary": {\n'
    '    "function_name": {\n'
    '      "total_scenarios": 5,\n'
    '      "branches_covered": ["voltage > MAX", "voltage < MIN", "ptr == NULL"],\n'
    '      "mc_dc_complete": true\n'
    "    }\n"
    "  }\n"
    "}\n"
)

SYSTEM_PROMPT_3A = (
    "You are a C test value generator for automotive AUTOSAR software.\n"
    "Your ONLY job is to assign concrete, compilable C values to every\n"
    "parameter of every test scenario.\n"
    "\n"
    "MANDATORY C89 VALUE RULES — follow exactly or the code will not compile:\n"
    "- uint8_t / uint8 / uint16 / uint32: MUST use u suffix → 5u, 255u, 0u\n"
    "- float / float32: MUST use f suffix → 3.14f, 0.0f, 150.0f\n"
    "- double / float64: NO suffix → 3.14, 0.0\n"
    "- BOOL / boolean: MUST use FALSE or TRUE → never false, true, 0, 1\n"
    "- Pointers (null test): MUST use NULL_PTR → never NULL, 0, nullptr\n"
    "- Struct params: specify EVERY field from struct_fields — leave NONE unset\n"
    "- Boundary values: use project #define constants when available\n"
    "  e.g. use MAX_SENSOR_CHANNELS not 32\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "test_cases": [\n'
    "    {\n"
    '      "scenario_id": "S001",\n'
    '      "function_name": "exact_name",\n'
    '      "inputs": {\n'
    '        "scalar_param": "42u",\n'
    '        "float_param": "3.14f",\n'
    '        "bool_param": "TRUE",\n'
    '        "struct_param": {\n'
    '          "field_one": "10u",\n'
    '          "field_two": "FALSE",\n'
    '          "field_three": "0.0f"\n'
    "        },\n"
    '        "pointer_param": "NULL_PTR"\n'
    "      },\n"
    '      "expected_return": "E_OK",\n'
    '      "expected_output_params": {\n'
    '        "output_ptr_param": "42u"\n'
    "      }\n"
    "    }\n"
    "  ]\n"
    "}\n"
)

SYSTEM_PROMPT_3B = (
    "You are a C value correctness critic for automotive test generation.\n"
    "Your ONLY job is to find value errors in test case inputs.\n"
    "\n"
    "Check every test case for these specific errors:\n"
    "\n"
    "C SUFFIX ERRORS:\n"
    "- uint8/uint16/uint32 values without u suffix → ERROR\n"
    "- float values without f suffix → ERROR\n"
    "- false/true used instead of FALSE/TRUE → ERROR\n"
    "- NULL used instead of NULL_PTR → ERROR\n"
    "\n"
    "STRUCT FIELD ERRORS:\n"
    "- Field names not in the type_map struct_fields → ERROR\n"
    "- Missing fields that are in struct_fields but not in inputs → ERROR\n"
    "- Field value wrong type for field's declared type → ERROR\n"
    "\n"
    "BOUNDARY ERRORS:\n"
    "- boundary_min scenario not actually at minimum value → ERROR\n"
    "- boundary_max scenario not actually at maximum value → ERROR\n"
    "- overflow scenario value not actually out of range → ERROR\n"
    "\n"
    "EXPECTED RETURN ERRORS:\n"
    "- expected_return is vague (depends/varies/unknown) → ERROR\n"
    "- expected_return wrong for scenario type → ERROR\n"
    "- null_ptr scenario expects E_OK (should be E_NOT_OK) → ERROR\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "fixes": [\n'
    "    {\n"
    '      "scenario_id": "S003",\n'
    '      "field_path": "inputs.act.is_engaged",\n'
    '      "current_value": "true",\n'
    '      "correct_value": "TRUE",\n'
    '      "reason": "BOOL type must use TRUE/FALSE not C++ bool literals"\n'
    "    }\n"
    "  ]\n"
    "}\n"
)

SYSTEM_PROMPT_3C = (
    "You are a test value finalizer for automotive C software.\n"
    "Your ONLY job is to apply all value fixes and output the corrected\n"
    "test cases. Then flag any scenarios that genuinely require hardware\n"
    "knowledge to determine correct expected values.\n"
    "\n"
    "Instructions:\n"
    "1. Start with the original test_cases from Call 3A\n"
    "2. Apply every fix from the fixes list in Call 3B\n"
    "3. For scenarios where the correct expected value depends on\n"
    "   hardware configuration not visible in the code:\n"
    '   set expected_return to "NEEDS_HUMAN" and explain why\n'
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "test_cases": [\n'
    "    {\n"
    '      "scenario_id": "S001",\n'
    '      "function_name": "exact_name",\n'
    '      "inputs": { ... complete inputs ... },\n'
    '      "expected_return": "E_OK",\n'
    '      "expected_output_params": {},\n'
    '      "needs_human_review": false,\n'
    '      "human_review_reason": null\n'
    "    }\n"
    "  ],\n"
    '  "needs_human_count": 0,\n'
    '  "corrections_applied": 3\n'
    "}\n"
)

SYSTEM_PROMPT_4A = (
    "You are a Cantata stub configuration specialist for automotive C testing.\n"
    "Your ONLY job is to specify stub setup for every test case.\n"
    "\n"
    "For each test case determine:\n"
    "1. Which HAL/RTE functions does the function under test call internally?\n"
    "   (look at the diff — these are calls inside the function body)\n"
    "2. What should each stub return for THIS specific test scenario?\n"
    "   - For normal tests: return success (HAL_OK, E_OK)\n"
    "   - For fault_injection tests: return failure to simulate the fault\n"
    "3. How many times should each stub be called in this test?\n"
    "4. Does the stub need to set any output parameters via pointer?\n"
    "\n"
    "CANTATA STUB SYNTAX REFERENCE:\n"
    "- INITIALISE_STUB_RETURN(function_name, return_value)\n"
    "- INITIALISE_STUB_POINTER_PARAM(function_name, param_name, value)\n"
    "- CHECK_N_CALLS(function_name, expected_count)\n"
    "\n"
    'Output ONLY this JSON:\n'
    "{\n"
    '  "stub_configs": [\n'
    "    {\n"
    '      "scenario_id": "S001",\n'
    '      "stubs": {\n'
    '        "HAL_ADC_Read": {\n'
    '          "return_value": "HAL_OK",\n'
    '          "expected_call_count": 1,\n'
    '          "output_params": {\n'
    '            "pData": "12000u"\n'
    "          }\n"
    "        }\n"
    "      }\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "\n"
    "If a test case involves no HAL calls: output empty stubs object for it.\n"
    "Include ALL scenarios even those with no stubs.\n"
)

SYSTEM_PROMPT_4B = (
    "You are a Cantata stub reviewer and finalizer for automotive C testing.\n"
    "Your job is to verify stub configurations are complete and correct,\n"
    "fix all issues, and output the final stub configuration.\n"
    "\n"
    "Verify each test case stub config:\n"
    "1. COMPLETENESS: Is every function from hal_functions list stubbed\n"
    "   in every test case? If the SUT calls it, it must be stubbed.\n"
    "2. CONSISTENCY: Does the stub return value match the scenario intent?\n"
    "   fault_injection → stub returns failure code\n"
    "   normal → stub returns success code\n"
    "3. CALL COUNT: Is the expected_call_count realistic?\n"
    "   0 is wrong if the function is called. 999 is wrong.\n"
    "4. OUTPUT PARAMS: If the HAL function sets values via pointer params,\n"
    "   are those output params configured?\n"
    "5. MISSING STUBS: Add any HAL function that the diff shows being called\n"
    "   but is missing from the stub config.\n"
    "\n"
    "Fix all issues. Output the complete corrected final stub configuration.\n"
    "\n"
    'Output ONLY this JSON (same structure as input):\n'
    "{\n"
    '  "stub_configs": [\n'
    "    {\n"
    '      "scenario_id": "S001",\n'
    '      "stubs": { ... complete corrected stubs ... }\n'
    "    }\n"
    "  ]\n"
    "}\n"
)

SYSTEM_PROMPT_5A = (
    "You are a JSON assembler for automotive test case generation.\n"
    "Your ONLY job is to merge all previous stage outputs into one\n"
    "complete, valid TestCaseFile JSON.\n"
    "\n"
    "You MUST follow this exact schema. Any deviation causes Stage 6 to fail.\n"
    "\n"
    "{\n"
    '  "version": "1.0",\n'
    '  "pr_number": "{pr_number}",\n'
    '  "module_name": "{module_name}",\n'
    '  "generated_at": "{timestamp}",\n'
    '  "functions": {\n'
    '    "function_name": {\n'
    '      "signature": "full C signature string",\n'
    '      "return_type": "C type",\n'
    '      "description": "plain English description",\n'
    '      "asil_level": "ASIL_B"\n'
    "    }\n"
    "  },\n"
    '  "hal_stubs": ["HAL_Function1", "HAL_Function2"],\n'
    '  "test_cases": [\n'
    "    {\n"
    '      "scenario_id": "S001",\n'
    '      "function_name": "exact_function_name",\n'
    '      "scenario": "descriptive scenario name",\n'
    '      "test_type": "normal",\n'
    '      "inputs": {\n'
    '        "param_name": "value_or_struct_dict"\n'
    "      },\n"
    '      "expected_return": "E_OK",\n'
    '      "expected_output_params": {},\n'
    '      "stubs": {\n'
    '        "HAL_Name": {\n'
    '          "return_value": "HAL_OK",\n'
    '          "expected_call_count": 1,\n'
    '          "output_params": {}\n'
    "        }\n"
    "      },\n"
    '      "asil_level": "ASIL_B",\n'
    '      "requirement_ref": ""\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "\n"
    "Output ONLY the JSON. No prose. No markdown. No explanation.\n"
)

SYSTEM_PROMPT_5B = (
    "You are a self-review auditor for automotive test case JSON.\n"
    "Your ONLY job is to check the assembled JSON for errors and fix them.\n"
    "\n"
    "Work through this checklist item by item. For each issue found:\n"
    "mark it in issues_found, fix it in the JSON, mark it in issues_fixed.\n"
    "\n"
    "CHECKLIST:\n"
    "□ 1. Every function_name in test_cases exists in the functions dict\n"
    "□ 2. Every struct input field exists in the type_map struct_fields\n"
    "     Remove any field that does NOT exist in struct_fields\n"
    "□ 3. Every param name in inputs exists in the function signature\n"
    "     Remove any param that does NOT exist in the signature\n"
    "□ 4. Every expected_return is a concrete C value\n"
    "     Replace depends/varies/unknown/tbd with E_NOT_OK\n"
    "□ 5. Every HAL function in hal_stubs is stubbed in every test_case\n"
    "     Add missing stubs with return_value E_OK and call_count 1\n"
    "□ 6. No duplicate scenario_ids\n"
    "     Renumber any duplicates\n"
    "□ 7. All test_type values are one of:\n"
    "     normal, boundary_min, boundary_max, null_ptr,\n"
    "     negative, overflow, fault_injection\n"
    "□ 8. All unsigned int literals have u suffix\n"
    "□ 9. All float literals have f suffix\n"
    "□ 10. All boolean values are FALSE or TRUE (not false/true/0/1)\n"
    "□ 11. All null pointer values are NULL_PTR (not NULL or 0)\n"
    "□ 12. No NEEDS_HUMAN in expected_return without needs_human_review: true\n"
    "\n"
    'Output the corrected JSON with self_review appended:\n'
    "{\n"
    "  ... corrected TestCaseFile JSON ...,\n"
    '  "self_review": {\n'
    '    "scenarios_planned": 8,\n'
    '    "test_cases_generated": 8,\n'
    '    "issues_found": ["S003: field \'pressure\' not in BrakeActuator_t"],\n'
    '    "issues_fixed": ["S003: removed unknown field \'pressure\'"],\n'
    '    "fields_removed": ["act.pressure"],\n'
    '    "stubs_added": [],\n'
    '    "values_corrected": ["S005.inputs.is_active: true → TRUE"]\n'
    "  }\n"
    "}\n"
)


# ---------------------------------------------------------------------------
# User prompt builder functions
# ---------------------------------------------------------------------------

def _build_1a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.function_signatures:
        parts.append(f"Function Signatures Confirmed by tree-sitter:\n{json.dumps(state.function_signatures, indent=2)}")
    parts.append(f"C Diff to Analyze:\n{state.diff_text}")
    if state.function_signatures:
        parts.append("Describe every function listed in the signatures above.")
    return "\n\n".join(parts)


def _build_1b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.function_signatures:
        parts.append(f"Function Signatures:\n{json.dumps(state.function_signatures, indent=2)}")
    if state.struct_definitions:
        parts.append(f"Struct Definitions — USE ONLY THESE FIELD NAMES:\n{json.dumps(state.struct_definitions, indent=2)}")
    if state.typedef_map:
        parts.append(f"Typedef Resolutions:\n{json.dumps(state.typedef_map, indent=2)}")
    if state.macro_constants:
        parts.append(f"Project Constants:\n{json.dumps(state.macro_constants, indent=2)}")
    parts.append("Build the complete type map. Output JSON only.")
    return "\n\n".join(parts)


def _build_1c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.code_analysis:
        parts.append(f"Code Analysis:\n{state.code_analysis}")
    if state.function_signatures:
        parts.append(f"Function Signatures:\n{json.dumps(state.function_signatures, indent=2)}")
    parts.append(f"C Diff:\n{state.diff_text}")
    parts.append("Classify every function. Output JSON only.")
    return "\n\n".join(parts)


def _build_2a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.code_analysis:
        parts.append(f"Code Analysis (what each function does):\n{state.code_analysis}")
    if state.type_map:
        parts.append(f"Type Map (parameter types and valid ranges):\n{json.dumps(state.type_map, indent=2)}")
    if state.complexity_tiers:
        parts.append(f"Complexity Classifications:\n{json.dumps(state.complexity_tiers, indent=2)}")
    parts.append("Plan comprehensive test scenarios. Think step by step. Output JSON only.")
    return "\n\n".join(parts)


def _build_2b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.code_analysis:
        parts.append(f"Code Analysis:\n{state.code_analysis}")
    if state.type_map:
        parts.append(f"Type Map:\n{json.dumps(state.type_map, indent=2)}")
    if state.scenarios_raw:
        parts.append(f"Scenario List to Review:\n{state.scenarios_raw if isinstance(state.scenarios_raw, str) else json.dumps(state.scenarios_raw, indent=2)}")
    parts.append("Find every gap. Output JSON only.")
    return "\n\n".join(parts)


def _build_2c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_raw:
        parts.append(f"Original Scenarios:\n{state.scenarios_raw if isinstance(state.scenarios_raw, str) else json.dumps(state.scenarios_raw, indent=2)}")
    if state.scenarios_critique:
        parts.append(f"Critique and Fixes:\n{state.scenarios_critique if isinstance(state.scenarios_critique, str) else json.dumps(state.scenarios_critique, indent=2)}")
    parts.append("Apply all fixes. Output final JSON only.")
    return "\n\n".join(parts)


def _build_3a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.scenarios_final:
        parts.append(f"Final Scenarios (assign values to each):\n{state.scenarios_final if isinstance(state.scenarios_final, str) else json.dumps(state.scenarios_final, indent=2)}")
    if state.type_map:
        parts.append(f"Type Map (use ONLY these field names and respect these valid ranges):\n{json.dumps(state.type_map, indent=2)}")
    if state.macro_constants:
        parts.append(f"Project Constants (use these for boundary values):\n{json.dumps(state.macro_constants, indent=2)}")
    parts.append("Assign concrete values. Output JSON only.")
    return "\n\n".join(parts)


def _build_3b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.type_map:
        parts.append(f"Type Map (ground truth for field names and types):\n{json.dumps(state.type_map, indent=2)}")
    if state.values_raw:
        parts.append(f"Test Cases to Review:\n{state.values_raw if isinstance(state.values_raw, str) else json.dumps(state.values_raw, indent=2)}")
    if state.macro_constants:
        parts.append(f"Project Constants:\n{json.dumps(state.macro_constants, indent=2)}")
    parts.append("Find every value error. Output JSON only.")
    return "\n\n".join(parts)


def _build_3c_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.values_raw:
        parts.append(f"Original Test Cases:\n{state.values_raw if isinstance(state.values_raw, str) else json.dumps(state.values_raw, indent=2)}")
    if state.values_critique:
        parts.append(f"Value Fixes to Apply:\n{state.values_critique if isinstance(state.values_critique, str) else json.dumps(state.values_critique, indent=2)}")
    parts.append("Apply all fixes. Output JSON only.")
    return "\n\n".join(parts)


def _build_4a_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.hal_functions:
        parts.append(f"HAL Functions That MUST Be Stubbed:\n{json.dumps(state.hal_functions, indent=2)}")
    parts.append(f"C Diff (shows internal function calls):\n{state.diff_text}")
    if state.values_final:
        parts.append(f"Final Test Cases:\n{state.values_final if isinstance(state.values_final, str) else json.dumps(state.values_final, indent=2)}")
    parts.append("Configure stubs for every scenario. Output JSON only.")
    return "\n\n".join(parts)


def _build_4b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.hal_functions:
        parts.append(f"HAL Functions List (all must be stubbed):\n{json.dumps(state.hal_functions, indent=2)}")
    parts.append(f"C Diff (shows which HAL functions are called):\n{state.diff_text}")
    if state.stubs_raw:
        parts.append(f"Stub Configs to Review and Fix:\n{state.stubs_raw if isinstance(state.stubs_raw, str) else json.dumps(state.stubs_raw, indent=2)}")
    parts.append("Verify, fix, and output final stub configs. JSON only.")
    return "\n\n".join(parts)


def _build_5a_user_prompt(state: PipelineState) -> str:
    parts = []
    parts.append("Merge these inputs:")
    if state.function_signatures:
        parts.append(f"[FUNCTIONS — from tree-sitter]:\n{json.dumps(state.function_signatures, indent=2)}")
    if state.type_map:
        parts.append(f"[TYPE MAP — Stage 1B]:\n{json.dumps(state.type_map, indent=2)}")
    if state.scenarios_final:
        parts.append(f"[FINAL SCENARIOS — Stage 2C]:\n{state.scenarios_final if isinstance(state.scenarios_final, str) else json.dumps(state.scenarios_final, indent=2)}")
    if state.values_final:
        parts.append(f"[FINAL TEST VALUES — Stage 3C]:\n{state.values_final if isinstance(state.values_final, str) else json.dumps(state.values_final, indent=2)}")
    if state.stubs_final:
        parts.append(f"[FINAL STUB CONFIGS — Stage 4B]:\n{state.stubs_final if isinstance(state.stubs_final, str) else json.dumps(state.stubs_final, indent=2)}")
    parts.append("Assemble into complete TestCaseFile JSON. Output JSON only.")
    return "\n\n".join(parts)


def _build_5b_user_prompt(state: PipelineState) -> str:
    parts = []
    if state.type_map:
        parts.append(f"Type Map (ground truth for field names):\n{json.dumps(state.type_map, indent=2)}")
    if state.hal_functions:
        parts.append(f"HAL Functions (all must be stubbed):\n{json.dumps(state.hal_functions, indent=2)}")
    if state.assembled_json:
        if isinstance(state.assembled_json, dict):
            parts.append(f"Assembled JSON to Audit:\n{json.dumps(state.assembled_json, indent=2)}")
        else:
            parts.append(f"Assembled JSON to Audit:\n{state.assembled_json}")
    parts.append("Audit, fix every issue, output corrected JSON with self_review. JSON only.")
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
    state = _run_stage_sequential(state, "2A_Scenario_Planner", SYSTEM_PROMPT_2A, _build_2a_user_prompt, "scenarios_raw", expect_json=True)
    state = _run_stage_sequential(state, "2B_Scenario_Critic", SYSTEM_PROMPT_2B, _build_2b_user_prompt, "scenarios_critique", expect_json=True)
    state = _run_stage_sequential(state, "2C_Scenario_Finalizer", SYSTEM_PROMPT_2C, _build_2c_user_prompt, "scenarios_final", expect_json=True)
    stage2_errors = _validate_stage_output(state, "2", ["scenarios_final"])
    if stage2_errors:
        state.validation_errors.extend(stage2_errors)

    # Stage 3: Sequential (3A -> 3B -> 3C)
    state = _run_stage_sequential(state, "3A_Value_Generator", SYSTEM_PROMPT_3A, _build_3a_user_prompt, "values_raw", expect_json=True)
    state = _run_stage_sequential(state, "3B_Value_Critic", SYSTEM_PROMPT_3B, _build_3b_user_prompt, "values_critique", expect_json=True)
    state = _run_stage_sequential(state, "3C_Value_Finalizer", SYSTEM_PROMPT_3C, _build_3c_user_prompt, "values_final", expect_json=True)
    stage3_errors = _validate_stage_output(state, "3", ["values_final"])
    if stage3_errors:
        state.validation_errors.extend(stage3_errors)

    # Stage 4: Sequential (4A -> 4B)
    state = _run_stage_sequential(state, "4A_Stub_Analyst", SYSTEM_PROMPT_4A, _build_4a_user_prompt, "stubs_raw", expect_json=True)
    state = _run_stage_sequential(state, "4B_Stub_Critic", SYSTEM_PROMPT_4B, _build_4b_user_prompt, "stubs_final", expect_json=True)
    stage4_errors = _validate_stage_output(state, "4", ["stubs_final"])
    if stage4_errors:
        state.validation_errors.extend(stage4_errors)

    # Stage 5: Sequential (5A -> 5B)
    state = _run_stage_sequential(state, "5A_JSON_Assembler", SYSTEM_PROMPT_5A, _build_5a_user_prompt, "assembled_json", expect_json=True)
    state = _run_stage_sequential(state, "5B_Self_Review", SYSTEM_PROMPT_5B, _build_5b_user_prompt, "self_review_result", expect_json=True)

    return state
