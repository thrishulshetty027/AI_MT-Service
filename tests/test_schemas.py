"""
Tests for Pydantic v2 schemas (TestType, StubConfig, TestCase, FunctionMeta, TestCaseFile)
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.schemas import (
    TestType,
    StubConfig,
    TestCase,
    FunctionMeta,
    TestCaseFile
)


class TestTestTypeEnum:
    """Test TestType enum"""

    def test_enum_has_all_values(self):
        """Test that TestType has exactly 7 values"""
        values = [t.value for t in TestType]
        assert len(values) == 7
        assert "NORMAL" in values
        assert "BOUNDARY_MIN" in values
        assert "BOUNDARY_MAX" in values
        assert "NULL_PTR" in values
        assert "NEGATIVE" in values
        assert "OVERFLOW" in values
        assert "FAULT_INJECTION" in values


class TestStubConfigModel:
    """Test StubConfig model"""

    def test_stub_config_basic(self):
        """Test basic StubConfig creation"""
        stub = StubConfig(return_value="42")
        assert stub.return_value == "42"
        assert stub.expected_call_count == 1
        assert stub.output_params == {}

    def test_stub_config_with_all_fields(self):
        """Test StubConfig with all fields"""
        stub = StubConfig(
            return_value="0",
            expected_call_count=2,
            output_params={"status": "OK"}
        )
        assert stub.return_value == "0"
        assert stub.expected_call_count == 2
        assert stub.output_params == {"status": "OK"}


class TestFunctionMetaModel:
    """Test FunctionMeta model"""

    def test_function_meta_basic(self):
        """Test basic FunctionMeta creation"""
        meta = FunctionMeta(
            signature="int add(int a, int b)",
            return_type="int",
            description="Adds two numbers"
        )
        assert meta.signature == "int add(int a, int b)"
        assert meta.return_type == "int"
        assert meta.description == "Adds two numbers"
        assert meta.asil_level == "ASIL_B"  # default

    def test_function_meta_custom_asil(self):
        """Test FunctionMeta with custom ASIL level"""
        meta = FunctionMeta(
            signature="void process(void)",
            return_type="void",
            description="Processes data",
            asil_level="ASIL_D"
        )
        assert meta.asil_level == "ASIL_D"


class TestCaseModel:
    """Test TestCase model validators"""

    def test_test_case_basic(self):
        """Test basic TestCase creation"""
        test = TestCase(
            scenario_id="TC001",
            function_name="add",
            scenario="Add two positive numbers",
            test_type=TestType.NORMAL,
            inputs={"a": "5", "b": "3"},
            expected_return="8"
        )
        assert test.scenario_id == "TC001"
        assert test.function_name == "add"
        assert test.test_type == TestType.NORMAL
        assert test.expected_return == "8"
        assert test.asil_level == "ASIL_B"
        assert test.needs_human_review is False

    def test_test_case_with_stubs(self):
        """Test TestCase with stubs"""
        test = TestCase(
            scenario_id="TC002",
            function_name="process",
            scenario="Process with HAL call",
            test_type=TestType.NORMAL,
            inputs={"data": "0x1000"},
            expected_return="SUCCESS",
            stubs={
                "HAL_Read": StubConfig(return_value="0x1000"),
                "HAL_Write": StubConfig(return_value="SUCCESS", expected_call_count=1)
            }
        )
        assert len(test.stubs) == 2
        assert "HAL_Read" in test.stubs
        assert "HAL_Write" in test.stubs

    def test_test_case_validator_rejects_vague_return_values(self):
        """Test that validator rejects vague expected_return values"""
        vague_values = ["depends", "varies", "unknown", "tbd", ""]
        for vague in vague_values:
            with pytest.raises(ValidationError) as exc_info:
                TestCase(
                    scenario_id="TC003",
                    function_name="test",
                    scenario="Test",
                    test_type=TestType.NORMAL,
                    inputs={},
                    expected_return=vague
                )
            assert "expected_return" in str(exc_info.value).lower()

    def test_test_case_validator_accepts_specific_return_values(self):
        """Test that validator accepts specific expected_return values"""
        valid_values = ["0", "0u", "0.0f", "SUCCESS", "ERROR_CODE", "NULL_PTR", "TRUE", "FALSE"]
        for valid in valid_values:
            test = TestCase(
                scenario_id="TC004",
                function_name="test",
                scenario="Test",
                test_type=TestType.NORMAL,
                inputs={},
                expected_return=valid
            )
            assert test.expected_return == valid

    def test_test_case_with_output_params(self):
        """Test TestCase with expected_output_params"""
        test = TestCase(
            scenario_id="TC005",
            function_name="process",
            scenario="Process with output params",
            test_type=TestType.NORMAL,
            inputs={"data": "0x1000"},
            expected_return="SUCCESS",
            expected_output_params={"status": "OK", "count": "5"}
        )
        assert test.expected_output_params == {"status": "OK", "count": "5"}

    def test_test_case_with_human_review(self):
        """Test TestCase with human review flags"""
        test = TestCase(
            scenario_id="TC006",
            function_name="test",
            scenario="Test",
            test_type=TestType.NORMAL,
            inputs={},
            expected_return="0",
            needs_human_review=True,
            human_review_reason="Complex logic requires manual verification"
        )
        assert test.needs_human_review is True
        assert test.human_review_reason == "Complex logic requires manual verification"


class TestCaseFileModel:
    """Test TestCaseFile model"""

    def test_test_case_file_basic(self):
        """Test basic TestCaseFile creation"""
        functions = {
            "add": FunctionMeta(
                signature="int add(int a, int b)",
                return_type="int",
                description="Adds two numbers"
            )
        }
        test_cases = [
            TestCase(
                scenario_id="TC001",
                function_name="add",
                scenario="Add two numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "5", "b": "3"},
                expected_return="8"
            )
        ]
        file = TestCaseFile(
            pr_number="TEST01",
            module_name="math",
            generated_at=datetime.now().isoformat(),
            functions=functions,
            test_cases=test_cases
        )
        assert file.version == "1.0"
        assert file.pr_number == "TEST01"
        assert file.module_name == "math"
        assert len(file.functions) == 1
        assert len(file.test_cases) == 1

    def test_validate_internal_consistency_missing_function(self):
        """Test validate_internal_consistency detects missing function"""
        functions = {
            "add": FunctionMeta(
                signature="int add(int a, int b)",
                return_type="int",
                description="Adds two numbers"
            )
        }
        test_cases = [
            TestCase(
                scenario_id="TC001",
                function_name="subtract",  # Function not in functions dict
                scenario="Subtract two numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "5", "b": "3"},
                expected_return="2"
            )
        ]
        file = TestCaseFile(
            pr_number="TEST01",
            module_name="math",
            generated_at=datetime.now().isoformat(),
            functions=functions,
            test_cases=test_cases
        )
        errors = file.validate_internal_consistency()
        assert len(errors) > 0
        assert any("subtract" in error for error in errors)

    def test_validate_internal_consistency_missing_stub(self):
        """Test validate_internal_consistency allows HAL stubs not used in every test case"""
        functions = {
            "process": FunctionMeta(
                signature="int process(int data)",
                return_type="int",
                description="Processes data"
            )
        }
        test_cases = [
            TestCase(
                scenario_id="TC001",
                function_name="process",
                scenario="Process with HAL call",
                test_type=TestType.NORMAL,
                inputs={"data": "0x1000"},
                expected_return="SUCCESS",
                stubs={"HAL_Read": StubConfig(return_value="0x1000")}
            )
        ]
        file = TestCaseFile(
            pr_number="TEST01",
            module_name="hal",
            generated_at=datetime.now().isoformat(),
            functions=functions,
            test_cases=test_cases,
            hal_stubs=["HAL_Read", "HAL_Write"]
        )
        errors = file.validate_internal_consistency()
        assert len(errors) == 0

    def test_validate_internal_consistency_duplicate_scenario_ids(self):
        """Test validate_internal_consistency detects duplicate scenario_ids"""
        functions = {
            "add": FunctionMeta(
                signature="int add(int a, int b)",
                return_type="int",
                description="Adds two numbers"
            )
        }
        test_cases = [
            TestCase(
                scenario_id="TC001",  # Duplicate
                function_name="add",
                scenario="Add two numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "5", "b": "3"},
                expected_return="8"
            ),
            TestCase(
                scenario_id="TC001",  # Duplicate
                function_name="add",
                scenario="Add two different numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "10", "b": "20"},
                expected_return="30"
            )
        ]
        file = TestCaseFile(
            pr_number="TEST01",
            module_name="math",
            generated_at=datetime.now().isoformat(),
            functions=functions,
            test_cases=test_cases
        )
        errors = file.validate_internal_consistency()
        assert len(errors) > 0
        assert any("duplicate" in error.lower() or "TC001" in error for error in errors)

    def test_validate_internal_consistency_valid(self):
        """Test validate_internal_consistency passes for valid TestCaseFile"""
        functions = {
            "add": FunctionMeta(
                signature="int add(int a, int b)",
                return_type="int",
                description="Adds two numbers"
            )
        }
        test_cases = [
            TestCase(
                scenario_id="TC001",
                function_name="add",
                scenario="Add two numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "5", "b": "3"},
                expected_return="8"
            ),
            TestCase(
                scenario_id="TC002",
                function_name="add",
                scenario="Add two different numbers",
                test_type=TestType.NORMAL,
                inputs={"a": "10", "b": "20"},
                expected_return="30"
            )
        ]
        file = TestCaseFile(
            pr_number="TEST01",
            module_name="math",
            generated_at=datetime.now().isoformat(),
            functions=functions,
            test_cases=test_cases
        )
        errors = file.validate_internal_consistency()
        assert len(errors) == 0
