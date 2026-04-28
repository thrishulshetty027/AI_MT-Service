"""
AI MT-Service: Cantata unit test generator for C code diffs from GitHub PRs.

Entry Points:
  python run.py --diff path/to/diff.txt --pr 167
    Full pipeline: Stage 1 -> testcases.md/json -> Stage 2 -> .c/.h

  python run.py --repo owner/repo --pr 167
    Fetch diff from GitHub -> full pipeline

  python run.py --stage2-only generated_tests/pr_167_testcases.json
    Skip Stage 1, regenerate .c/.h from existing JSON

  python run.py --stage1-only --diff path/to/diff.txt --pr 167
    Run only Stage 1: produce testcases.md/json, stop before C generation

Environment:
  REQUIRE_HUMAN_APPROVAL=true
    After Stage 1: print testcases.md location, prompt to proceed.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(override=True)

GENERATED_FOLDER = "generated_tests"


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def fetch_diff_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def fetch_diff_from_github(repo_name: str, pr_number: int) -> str:
    import requests

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in .env")

    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    diff_url = resp.json().get("diff_url")
    if not diff_url:
        raise RuntimeError(f"No diff_url for PR #{pr_number}")

    diff_resp = requests.get(diff_url)
    diff_resp.raise_for_status()
    return diff_resp.text


def run_full_pipeline(diff_text: str, pr_number: str, verbose: bool = False) -> dict:
    """
    Full pipeline: Stage 1 (LLM) -> Stage 2 (code gen) -> compile -> quality gates.
    """
    setup_logging(verbose)

    print(f"\n{'=' * 60}")
    print(f"  AI MT-Service — Full Pipeline — PR #{pr_number}")
    print(f"{'=' * 60}")

    print("\n[Stage 1] Running 13-LLM call pipeline...")
    from src.stage1_generator import run_stage1

    tc_file, state = run_stage1(diff_text, pr_number)
    print(f"  Generated {len(tc_file.test_cases)} test cases for {len(tc_file.functions)} functions")

    md_path = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}_testcases.md")
    print(f"  Test cases markdown: {md_path}")

    require_approval = os.getenv("REQUIRE_HUMAN_APPROVAL", "").lower() == "true"
    if require_approval:
        print(f"\n  Review test cases: {md_path}")
        response = input("  Proceed to Stage 2 code generation? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            print("  Aborted by user.")
            return {"status": "aborted", "pr_number": pr_number}

    print("\n[Stage 2] Generating C code via templates...")
    json_path = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}_testcases.json")
    result = run_stage2_pipeline(json_path, state.type_map, state.typedef_map, pr_number, verbose)

    return {
        "status": "complete",
        "pr_number": pr_number,
        "test_cases": len(tc_file.test_cases),
        "functions": len(tc_file.functions),
        **result,
    }


def run_stage1_only(diff_text: str, pr_number: str, verbose: bool = False) -> dict:
    """Run only Stage 1: produce testcases.md/json, stop before C generation."""
    setup_logging(verbose)

    print(f"\n{'=' * 60}")
    print(f"  Stage 1 Only — PR #{pr_number}")
    print(f"{'=' * 60}")

    from src.stage1_generator import run_stage1

    tc_file, state = run_stage1(diff_text, pr_number)
    print(f"\n  Generated {len(tc_file.test_cases)} test cases for {len(tc_file.functions)} functions")
    print(f"  Output: generated_tests/pr_{pr_number}_testcases.md")
    print(f"  Output: generated_tests/pr_{pr_number}_testcases.json")

    return {
        "status": "stage1_complete",
        "pr_number": pr_number,
        "test_cases": len(tc_file.test_cases),
        "functions": len(tc_file.functions),
    }


def run_stage2_pipeline(
    json_path: str,
    type_map: dict = None,
    typedef_map: dict = None,
    pr_number: str = None,
    verbose: bool = False,
) -> dict:
    """Run Stage 2: load JSON, generate C, compile, quality gates."""
    from src.stage2_generator import run_stage2, load_testcase_file
    from src.compile_validator import run_compile_loop, write_compile_report
    from src.quality_gates import run_cppcheck, generate_traceability, write_trace

    os.makedirs(GENERATED_FOLDER, exist_ok=True)

    print("\n  [Stage 2a] Loading testcases.json...")
    stage2_result = run_stage2(json_path, type_map, typedef_map)
    c_path = stage2_result["test_script_c"]
    h_path = stage2_result["header_h"]
    print(f"  Generated: {c_path}")
    print(f"  Generated: {h_path}")

    tc_file = load_testcase_file(json_path)
    pr = pr_number or tc_file.pr_number

    print("\n  [Stage 2b] Running cppcheck...")
    cppcheck_result = run_cppcheck(c_path)
    if cppcheck_result.get("skipped"):
        print("  cppcheck not available — skipped")
    elif cppcheck_result["issue_count"] > 0:
        print(f"  cppcheck found {cppcheck_result['issue_count']} issue(s)")
    else:
        print("  cppcheck: no issues found")

    print("\n  [Stage 2c] Compiling with MSVC17...")
    compile_result = run_compile_loop(c_path, json_path, type_map or {})
    if compile_result.get("success"):
        print(f"  Compilation succeeded (attempt {compile_result['attempts']})")
    else:
        print(f"  Compilation failed after {compile_result['attempts']} attempt(s)")

    report_path = write_compile_report(pr, compile_result)
    print(f"  Compile report: {report_path}")

    print("\n  [Stage 2d] Generating traceability sidecar...")
    tc_dict = json.loads(tc_file.model_dump_json())
    trace = generate_traceability(tc_dict, pr, tc_file.module_name, compile_result, cppcheck_result)
    trace_path = write_trace(trace, pr)
    print(f"  Traceability: {trace_path}")

    print(f"\n{'=' * 60}")
    print(f"  PR #{pr} complete")
    print(f"{'=' * 60}")

    return {
        "c_file": c_path,
        "h_file": h_path,
        "compile_report": report_path,
        "trace_file": trace_path,
        "compile_success": compile_result.get("success", False),
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI MT-Service: Cantata test generator for automotive C code"
    )
    parser.add_argument("--diff", help="Path to a diff file to process")
    parser.add_argument("--pr", help="PR number identifier")
    parser.add_argument("--repo", help="GitHub repo (owner/name)")
    parser.add_argument("--stage1-only", action="store_true", help="Run only Stage 1 (LLM pipeline)")
    parser.add_argument("--stage2-only", help="Path to testcases.json — skip Stage 1, regenerate .c/.h")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    print("=" * 60)
    print("  AI MT-Service — Cantata Test Generator")
    print("=" * 60)

    if args.stage2_only:
        if not os.path.exists(args.stage2_only):
            print(f"\nError: file not found: {args.stage2_only}")
            return 1
        pr = args.pr or "unknown"
        result = run_stage2_pipeline(args.stage2_only, pr_number=pr, verbose=args.verbose)
        print(f"\nDone. Output: {result['c_file']}")
        return 0

    if args.diff:
        diff_text = fetch_diff_from_file(args.diff)
        pr_number = args.pr or os.path.splitext(os.path.basename(args.diff))[0].replace("pr_", "")

        if args.stage1_only:
            result = run_stage1_only(diff_text, pr_number, verbose=args.verbose)
            return 0

        result = run_full_pipeline(diff_text, pr_number, verbose=args.verbose)
        if result.get("status") == "aborted":
            return 0
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
        return 0 if result.get("status") == "complete" else 1

    if args.repo and args.pr:
        diff_text = fetch_diff_from_github(args.repo, int(args.pr))
        result = run_full_pipeline(diff_text, args.pr, verbose=args.verbose)
        return 0 if result.get("status") == "complete" else 1

    print("\nUsage:")
    print("  python run.py --diff path/to/diff.txt --pr 167")
    print("  python run.py --repo owner/repo --pr 167")
    print("  python run.py --stage2-only generated_tests/pr_167_testcases.json")
    print("  python run.py --stage1-only --diff path/to/diff.txt --pr 167")
    return 1


if __name__ == "__main__":
    sys.exit(main())
