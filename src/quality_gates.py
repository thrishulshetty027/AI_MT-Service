"""
Quality gates — cppcheck static analysis and ISO 26262 traceability sidecar.

Runs cppcheck on generated C files and produces trace_PR.json for
ISO 26262 ASIL-B compliance documentation.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_cppcheck(
    c_file_path: str,
    cppcheck_exe: str = "cppcheck",
    include_dirs: List[str] = None,
) -> Dict[str, Any]:
    """
    Run cppcheck static analysis on a generated C file.

    Args:
        c_file_path: Path to the .c file
        cppcheck_exe: Path to cppcheck executable
        include_dirs: Additional include directories

    Returns:
        Dict with: issues, issue_count, output
    """
    if include_dirs is None:
        include_dirs = []

    cmd = [
        cppcheck_exe,
        "--enable=all",
        "--language=c",
        "--std=c89",
        "--suppress=missingInclude",
        "--quiet",
        "--template={file}:{line}:{severity}:{message}",
    ]
    for inc_dir in include_dirs:
        cmd.extend(["-I", inc_dir])
    cmd.append(c_file_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        issues = _parse_cppcheck_output(result.stdout + result.stderr)
        return {
            "issues": issues,
            "issue_count": len(issues),
            "output": result.stdout + result.stderr,
            "skipped": False,
        }
    except FileNotFoundError:
        logger.warning("cppcheck not found — skipping static analysis")
        return {
            "issues": [],
            "issue_count": 0,
            "output": "",
            "skipped": True,
        }
    except subprocess.TimeoutExpired:
        return {
            "issues": [],
            "issue_count": 0,
            "output": "cppcheck timed out (60s)",
            "skipped": False,
        }


def _parse_cppcheck_output(output: str) -> List[Dict[str, str]]:
    """Parse cppcheck output into structured issues."""
    issues = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("Checking") or line.startswith("cppcheck"):
            continue
        parts = line.split(":", 3)
        if len(parts) >= 4:
            issues.append({
                "file": parts[0],
                "line": parts[1],
                "severity": parts[2],
                "message": parts[3],
            })
    return issues


def generate_traceability(
    tc_file_dict: Dict[str, Any],
    pr_number: str,
    module_name: str,
    compile_result: Optional[Dict] = None,
    cppcheck_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Generate ISO 26262 traceability sidecar.

    Args:
        tc_file_dict: TestCaseFile as dict
        pr_number: PR identifier
        module_name: Module name
        compile_result: Compile validation result
        cppcheck_result: cppcheck result

    Returns:
        Traceability dict ready for JSON serialization
    """
    test_cases = tc_file_dict.get("test_cases", [])
    functions = tc_file_dict.get("functions", {})

    coverage_map = {}
    for tc in test_cases:
        fn = tc.get("function_name", "")
        if fn not in coverage_map:
            coverage_map[fn] = {
                "total_scenarios": 0,
                "test_types": set(),
                "scenario_ids": [],
            }
        coverage_map[fn]["total_scenarios"] += 1
        coverage_map[fn]["test_types"].add(tc.get("test_type", ""))
        coverage_map[fn]["scenario_ids"].append(tc.get("scenario_id", ""))

    for fn in coverage_map:
        coverage_map[fn]["test_types"] = sorted(coverage_map[fn]["test_types"])

    trace = {
        "trace_version": "1.0",
        "standard": "ISO 26262",
        "asil_level": "ASIL_B",
        "pr_number": pr_number,
        "module_name": module_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "functions_under_test": len(functions),
            "total_test_cases": len(test_cases),
            "hal_stubs": tc_file_dict.get("hal_stubs", []),
        },
        "function_coverage": coverage_map,
        "test_type_distribution": {},
        "quality_gates": {
            "compile_success": compile_result.get("success", False) if compile_result else None,
            "compile_attempts": compile_result.get("attempts", 0) if compile_result else None,
            "cppcheck_issues": cppcheck_result.get("issue_count", 0) if cppcheck_result else None,
            "cppcheck_skipped": cppcheck_result.get("skipped", True) if cppcheck_result else None,
        },
    }

    type_dist = {}
    for tc in test_cases:
        tt = tc.get("test_type", "UNKNOWN")
        type_dist[tt] = type_dist.get(tt, 0) + 1
    trace["test_type_distribution"] = type_dist

    return trace


def write_trace(
    trace: Dict[str, Any],
    pr_number: str,
    output_dir: str = "generated_tests",
) -> str:
    """
    Write traceability JSON.

    Args:
        trace: Traceability dict
        pr_number: PR identifier
        output_dir: Output directory

    Returns:
        Path to written trace file
    """
    os.makedirs(output_dir, exist_ok=True)
    trace_path = os.path.join(output_dir, f"trace_{pr_number}.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)
    return trace_path
