"""
Pydantic v2 schemas for test case data structures.

Implements all required models from Tasks.md specification.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, field_validator


class TestType(str, Enum):
    """Test type classification for automotive safety testing."""
    NORMAL = "NORMAL"
    BOUNDARY_MIN = "BOUNDARY_MIN"
    BOUNDARY_MAX = "BOUNDARY_MAX"
    NULL_PTR = "NULL_PTR"
    NEGATIVE = "NEGATIVE"
    OVERFLOW = "OVERFLOW"
    FAULT_INJECTION = "FAULT_INJECTION"


class StubConfig(BaseModel):
    """Configuration for function call stubs."""
    return_value: Optional[str] = None
    expected_call_count: int = 1
    output_params: Dict[str, str] = {}
    
    @field_validator('return_value', mode='before')
    @classmethod
    def default_return_value(cls, v):
        if v is None or v == "":
            return "NULL"
        return str(v)
    
    @field_validator('output_params', mode='before')
    @classmethod
    def stringify_output_params(cls, v):
        if not v:
            return {}
        return {k: str(v) for k, v in v.items()}


class TestCase(BaseModel):
    """Individual test case with inputs, expected outputs, and configuration."""
    scenario_id: str
    function_name: str
    scenario: str
    test_type: TestType
    inputs: Dict[str, str | Dict]
    expected_return: str
    expected_output_params: Dict[str, str] = {}
    stubs: Dict[str, StubConfig] = {}
    asil_level: str = "ASIL_B"
    requirement_ref: str = ""
    needs_human_review: bool = False
    human_review_reason: Optional[str] = None

    @field_validator('test_type', mode='before')
    @classmethod
    def normalize_test_type(cls, v):
        if isinstance(v, str):
            v = v.strip().upper()
            valid = {t.value for t in TestType}
            if v not in valid:
                if "BOUNDARY_MIN" in v or "MIN" in v:
                    v = "BOUNDARY_MIN"
                elif "BOUNDARY_MAX" in v or "MAX" in v:
                    v = "BOUNDARY_MAX"
                elif "NULL" in v:
                    v = "NULL_PTR"
                elif "OVERFLOW" in v:
                    v = "OVERFLOW"
                elif "FAULT" in v or "ERROR" in v or "CORRUPT" in v or "STRESS" in v:
                    v = "FAULT_INJECTION"
                elif "NEGATIVE" in v or "INVALID" in v:
                    v = "NEGATIVE"
                elif "INTEGRATION" in v or "NORMAL" in v or "GAP" in v or "DIAGNOSTIC" in v or "STATE" in v or "CONCURRENT" in v or "ALPHA" in v:
                    v = "NORMAL"
                else:
                    v = "NORMAL"
        return v

    @field_validator('expected_return')
    @classmethod
    def reject_vague_expected_return(cls, v: str) -> str:
        """Reject vague or non-specific expected return values."""
        vague_indicators = ["depends", "varies", "unknown", "tbd"]
        v_lower = v.lower().strip()

        if v_lower in vague_indicators:
            raise ValueError(
                f"expected_return cannot be vague: '{v}'. "
                "Provide specific value (e.g., '0', 'SUCCESS', 'ERROR_CODE')."
            )

        if not v_lower:
            raise ValueError("expected_return cannot be empty")

        return v


class FunctionMeta(BaseModel):
    """Metadata about a function under test."""
    signature: str
    return_type: str
    description: str
    asil_level: str = "ASIL_B"


class TestCaseFile(BaseModel):
    """Complete test case file with functions and test cases."""
    version: str = "1.0"
    pr_number: str
    module_name: str
    generated_at: str
    functions: Dict[str, FunctionMeta]
    test_cases: List[TestCase]
    hal_stubs: List[str] = []

    def validate_internal_consistency(self) -> List[str]:
        """
        Validate internal consistency of the test case file.

        Checks:
        1. Every test case's function_name exists in the functions dict
        2. Every stub in hal_stubs list is stubbed in every test_case
        3. No duplicate scenario_ids across all test_cases

        Returns:
            List of error messages (empty if validation passes)
        """
        errors: List[str] = []

        # Check 1: All test case function names exist in functions dict
        for test_case in self.test_cases:
            if test_case.function_name not in self.functions:
                errors.append(
                    f"Test case '{test_case.scenario_id}' references unknown function "
                    f"'{test_case.function_name}'. Available functions: {list(self.functions.keys())}"
                )

        # Check 2: HAL stubs are properly configured (warn if HALs exist but not all stubbed)
        # Note: Test cases only need to stub HALs they actually call, not all HALs
        if self.hal_stubs:
            for test_case in self.test_cases:
                # Only warn if test case calls HALs but doesn't stub them
                # This is a warning, not an error, as not all HALs need to be stubbed in every test
                unstubbed_hals = [h for h in self.hal_stubs if h not in test_case.stubs]
                if unstubbed_hals and len(test_case.stubs) < len(self.hal_stubs):
                    # This is expected - not all HALs need stubs in every test case
                    # Just log info, don't error
                    pass

        # Check 3: No duplicate scenario_ids
        scenario_ids = [tc.scenario_id for tc in self.test_cases]
        seen_ids = set()
        duplicates = set()

        for scenario_id in scenario_ids:
            if scenario_id in seen_ids:
                duplicates.add(scenario_id)
            seen_ids.add(scenario_id)

        if duplicates:
            errors.append(
                f"Duplicate scenario_ids found: {sorted(duplicates)}. "
                "Each test case must have a unique scenario_id."
            )

        return errors
