from pydantic import BaseModel, ConfigDict
from src.ir_models import TestCase, FunctionSignature, Parameter


class ResolvedTestCase(BaseModel):
    model_config = ConfigDict(strict=False)

    test_id: str
    function_name: str
    scenario: str = ""
    input_values: dict[str, str] = {}
    expected_result: str = ""
    test_type: str = "normal"
    resolved_types: dict[str, str] = {}
    return_type: str = "int"
    declarations: dict[str, str] = {}

    @property
    def signature(self) -> FunctionSignature | None:
        return self._signature

    def __init__(self, _signature: FunctionSignature | None = None, **data):
        super().__init__(**data)
        self._signature = _signature


_STRIP_SUFFIXES = ("_value", "_input", "_var", "_buffer", "_result")


def _match_param_name(var_name: str, params: list[Parameter]) -> Parameter | None:
    if not var_name:
        return None

    for p in params:
        if p.name == var_name:
            return p

    for suffix in _STRIP_SUFFIXES:
        if var_name.endswith(suffix):
            stripped = var_name[: -len(suffix)]
            for p in params:
                if p.name == stripped:
                    return p

    for p in params:
        if var_name.startswith(p.name) or p.name.startswith(var_name):
            return p

    for p in params:
        for suffix in _STRIP_SUFFIXES:
            if var_name.endswith("_" + p.name + suffix):
                return p
        if var_name.endswith("_" + p.name):
            return p

    return None


def resolve_types(
    test_cases: list[TestCase],
    signatures: list[FunctionSignature],
) -> list[ResolvedTestCase]:
    sig_lookup: dict[str, FunctionSignature] = {s.name: s for s in signatures}
    resolved: list[ResolvedTestCase] = []

    for tc in test_cases:
        sig = sig_lookup.get(tc.function_name)
        if sig is None:
            raise ValueError(f"Unknown function: {tc.function_name}")

        resolved_types: dict[str, str] = {}
        for var_name in tc.input_values:
            param = _match_param_name(var_name, sig.parameters)
            if param:
                resolved_types[var_name] = param.c_type
            else:
                resolved_types[var_name] = "unknown"

        resolved.append(ResolvedTestCase(
            _signature=sig,
            test_id=tc.test_id,
            function_name=tc.function_name,
            scenario=tc.scenario,
            input_values=tc.input_values,
            expected_result=tc.expected_result,
            test_type=tc.test_type,
            resolved_types=resolved_types,
            return_type=sig.return_type,
            declarations=tc.declarations,
        ))

    return resolved


def get_unresolved_variables(resolved: ResolvedTestCase) -> list[str]:
    return [k for k, v in resolved.resolved_types.items() if v == "unknown"]


def get_missing_variables(resolved: ResolvedTestCase) -> list[str]:
    if resolved._signature is None:
        return []
    param_names = {p.name for p in resolved._signature.parameters}
    return sorted(param_names - set(resolved.input_values.keys()))
