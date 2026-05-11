
import argparse
import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(override=True)

GENERATED_FOLDER = "generated_tests"
PROCESSED_FILE = "processed_prs.json"


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


def load_processed_prs():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [item if isinstance(item, int) else item.get("pr_number", 0) for item in data if isinstance(item, (int, dict))]
        except (json.JSONDecodeError, Exception):
            return []
    return []


def save_processed_prs(processed_prs):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed_prs, f, indent=4)


def poll_latest_pr(repo_name: str):
    import requests

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in .env")

    label = os.getenv("PR_LABEL", "ai-test")
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    print(f"\n  Polling {repo_name} for PRs with label '{label}'...")
    url = f"https://api.github.com/repos/{repo_name}/issues"
    resp = requests.get(url, headers=headers, params={"state": "open", "labels": label})
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API error: {resp.status_code} {resp.text}")

    prs = [issue for issue in resp.json() if "pull_request" in issue]
    if not prs:
        print(f"  No open PRs with label '{label}' found in {repo_name}")
        return None, None

    processed = load_processed_prs()
    for pr in prs:
        pr_number = pr["number"]
        if pr_number in processed:
            print(f"  PR #{pr_number} already processed — skipping")
            continue
        print(f"  Found new PR #{pr_number}: {pr.get('title', '(no title)')}")
        return repo_name, pr_number

    print("  All labeled PRs already processed")
    return None, None


def run_full_pipeline(diff_text: str, pr_number: str, verbose: bool = False) -> dict:
    """
    Full pipeline: Stage 1 (LLM) -> Stage 2 (code gen) -> compile -> quality gates.
    """
    setup_logging(verbose)

    os.makedirs(GENERATED_FOLDER, exist_ok=True)

    diff_path = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}.diff")
    with open(diff_path, "w", encoding="utf-8") as f:
        f.write(diff_text)
    print(f"  Saved diff: {diff_path}")

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
    result = run_stage2_pipeline(
        json_path, state.type_map, state.typedef_map, pr_number, verbose,
        function_signatures=state.function_signatures,
    )

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
    function_signatures: list = None,
) -> dict:
    """Run Stage 2: load JSON, generate C, compile, quality gates."""
    from src.stage2_generator import run_stage2, load_testcase_file
    from src.compile_validator import run_compile_loop, write_compile_report
    from src.quality_gates import run_cppcheck, generate_traceability, write_trace

    os.makedirs(GENERATED_FOLDER, exist_ok=True)

    print("\n  [Stage 2a] Loading testcases.json...")
    stage2_result = run_stage2(json_path, type_map, typedef_map, function_signatures=function_signatures)
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
        # Save cppcheck issues to file
        cppcheck_path = os.path.join(GENERATED_FOLDER, f"cppcheck_{pr}.txt")
        with open(cppcheck_path, "w", encoding="utf-8") as f:
            for issue in cppcheck_result.get("issues", []):
                f.write(f"{issue['file']}:{issue['line']}:{issue['severity']}:{issue['message']}\n")
        print(f"  Cppcheck issues saved to: {cppcheck_path}")
    else:
        print("  cppcheck: no issues found")

    print("\n  [Stage 2c] Compiling with MSVC17...")
    compile_result = run_compile_loop(c_path, json_path, type_map or {})
    if compile_result.get("skipped"):
        print(f"  Compilation skipped (cl.exe not available)")
    elif compile_result.get("success"):
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
    parser.add_argument("diff_file", nargs="?", help="Diff file to process (e.g., pr_179.diff)")
    parser.add_argument("pr_name", nargs="?", help="PR identifier (defaults to filename)")
    parser.add_argument("--diff", help="Path to a diff file to process (legacy)")
    parser.add_argument("--pr", help="PR number identifier (legacy)")
    parser.add_argument("--repo", help="GitHub repo (owner/name) — defaults to GITHUB_REPO from .env")
    parser.add_argument("--stage1-only", action="store_true", help="Run only Stage 1 (LLM pipeline)")
    parser.add_argument("--stage2-only", help="Path to testcases.json — skip Stage 1, regenerate .c/.h")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    print("=" * 60)
    print("  AI MT-Service — Cantata Test Generator")
    print("=" * 60)

    # Stage 2 only mode
    if args.stage2_only:
        if not os.path.exists(args.stage2_only):
            print(f"\nError: file not found: {args.stage2_only}")
            return 1
        pr = args.pr or "unknown"
        result = run_stage2_pipeline(args.stage2_only, pr_number=pr, verbose=args.verbose)
        print(f"\nDone. Output: {result['c_file']}")
        return 0

    # New simple mode: python run.py pr_179.diff [MANUAL_179]
    if args.diff_file:
        diff_path = os.path.join("generated_tests", args.diff_file)
        if not os.path.exists(diff_path):
            print(f"\nError: Diff file not found: {diff_path}")
            return 1
        
        with open(diff_path, encoding="utf-8") as f:
            diff_text = f.read()
        
        pr_number = args.pr_name or os.path.splitext(args.diff_file)[0]
        print(f"\n  Processing diff file: {args.diff_file}")

        if args.stage1_only:
            result = run_stage1_only(diff_text, pr_number, verbose=args.verbose)
            return 0

    # New simple mode: python run.py pr_179.diff [MANUAL_179]
    if args.diff_file:
        diff_path = os.path.join("generated_tests", args.diff_file)
        if not os.path.exists(diff_path):
            print(f"\nError: Diff file not found: {diff_path}")
            return 1
        
        with open(diff_path, encoding="utf-8") as f:
            diff_text = f.read()
        
        pr_number = args.pr_name or os.path.splitext(args.diff_file)[0]
        print(f"\n  Processing diff file: {args.diff_file}")

        if args.stage1_only:
            result = run_stage1_only(diff_text, pr_number, verbose=args.verbose)
            return 0

        result = run_full_pipeline(diff_text, pr_number, verbose=args.verbose)
        if result.get("status") == "aborted":
            return 0
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
        return 0 if result.get("status") == "complete" else 1

    # Legacy --diff mode (backward compatibility)
    if args.diff:
        diff_text = fetch_diff_from_file(args.diff)
        pr_number = args.pr or os.path.splitext(os.path.basename(args.diff))[0].replace("pr_", "")
        print(f"\n  Processing diff file: {args.diff}")

        if args.stage1_only:
            result = run_stage1_only(diff_text, pr_number, verbose=args.verbose)
            return 0

        result = run_full_pipeline(diff_text, pr_number, verbose=args.verbose)
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
        return 0 if result.get("status") == "complete" else 1

    # Legacy --diff mode (backward compatibility)
    if args.diff:
        diff_text = fetch_diff_from_file(args.diff)
        pr_number = args.pr or os.path.splitext(os.path.basename(args.diff))[0].replace("pr_", "")
        print(f"\n  Processing diff file: {args.diff}")

        if args.stage1_only:
            result = run_stage1_only(diff_text, pr_number, verbose=args.verbose)
            return 0

        result = run_full_pipeline(diff_text, pr_number, verbose=args.verbose)
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
        return 0 if result.get("status") == "complete" else 1

    # Explicit --repo --pr mode
    if args.repo and args.pr:
        diff_text = fetch_diff_from_github(args.repo, int(args.pr))
        result = run_full_pipeline(diff_text, args.pr, verbose=args.verbose)
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
        return 0 if result.get("status") == "complete" else 1

    # Default: no arguments — poll GitHub for latest labeled PR and run full pipeline
    repo_name = args.repo or os.getenv("GITHUB_REPO")
    if not repo_name:
        print("\nError: No GITHUB_REPO in .env and no --repo given.")
        print("  Either set GITHUB_REPO=owner/repo in .env or pass --repo owner/repo --pr 123")
        return 1

    repo_name, pr_number = poll_latest_pr(repo_name)
    if not pr_number:
        return 0

    print(f"\n  Downloading diff for PR #{pr_number}...")
    diff_text = fetch_diff_from_github(repo_name, pr_number)

    result = run_full_pipeline(diff_text, str(pr_number), verbose=args.verbose)
    if result.get("status") == "complete":
        processed = load_processed_prs()
        if pr_number not in processed:
            processed.append(pr_number)
        save_processed_prs(processed)
        print(f"  PR #{pr_number} marked as processed")
        if result.get("c_file"):
            print(f"\nDone. Output: {result['c_file']}")
    return 0 if result.get("status") == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
