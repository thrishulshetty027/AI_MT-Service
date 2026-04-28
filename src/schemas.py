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
    return_value: str
    expected_call_count: int = 1
    output_params: Dict[str, str] = {}


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

        # Check 2: Every HAL stub is stubbed in every test case
        if self.hal_stubs:
            for test_case in self.test_cases:
                for hal_stub in self.hal_stubs:
                    if hal_stub not in test_case.stubs:
                        errors.append(
                            f"Test case '{test_case.scenario_id}' does not stub required HAL function "
                            f"'{hal_stub}'. Required HAL stubs: {self.hal_stubs}"
                        )

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
