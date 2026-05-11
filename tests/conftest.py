import os
import pytest


@pytest.fixture(autouse=True)
def _isolated_generated_dir(tmp_path, monkeypatch, request):
    test_dir = str(tmp_path / "generated_tests")
    os.makedirs(test_dir, exist_ok=True)

    import src.stage1_generator as s1
    import src.stage2_generator as s2
    import src.compile_validator as cv
    import src.quality_gates as qg

    monkeypatch.setattr(s1, "GENERATED_TESTS_DIR", test_dir)
    monkeypatch.setattr(s2, "GENERATED_TESTS_DIR", test_dir)
    monkeypatch.setattr(cv, "GENERATED_TESTS_DIR", test_dir)
    monkeypatch.setattr(qg, "GENERATED_TESTS_DIR", test_dir)

    if hasattr(request.module, "GENERATED_TESTS_DIR"):
        monkeypatch.setattr(request.module, "GENERATED_TESTS_DIR", test_dir)
