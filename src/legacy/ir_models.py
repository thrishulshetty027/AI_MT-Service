from pydantic import BaseModel, ConfigDict, field_validator


class Parameter(BaseModel):
    model_config = ConfigDict(strict=False)

    name: str
    c_type: str
    is_pointer: bool = False
    is_array: bool = False
    base_type: str


class FunctionSignature(BaseModel):
    model_config = ConfigDict(strict=False)

    name: str
    return_type: str
    is_pointer_return: bool = False
    is_static: bool = False
    parameters: list["Parameter"]


class TestCaseModel(BaseModel):
    model_config = ConfigDict(strict=False)

    test_id: str
    function_name: str
    scenario: str = ""
    input_values: dict[str, str] = {}
    expected_result: str = ""
    test_type: str = "normal"
    declarations: dict[str, str] = {}

    @field_validator("function_name")
    @classmethod
    def function_name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("function_name must not be empty")
        return v


class TestSuiteIR(BaseModel):
    model_config = ConfigDict(strict=False)

    pr_number: str
    function_signatures: list["FunctionSignature"]
    test_cases: list["TestCaseModel"] = []


TestCase = TestCaseModel
