import os
import sys
import re
from datetime import datetime
import requests
from dotenv import load_dotenv

from testcase_generator import generate_testcases

load_dotenv()

GENERATED_FOLDER = "generated_tests"
PROCESSED_FILE = "processed_prs.json"


DIFF_FILE = "generated_tests/pr_diff.txt"
OUTPUT_FILE = "generated_tests/module_testcases.md"


def get_pr_diff_files():
    """
    Get PR diff files from the generated_tests folder.
    IMPORTANT: Only returns .diff files, not test case or module test files.
    """
    if not os.path.exists(GENERATED_FOLDER):
        return []
    return [f for f in os.listdir(GENERATED_FOLDER)
            if f.endswith(".diff") and
            not f.endswith("_testcases.md") and
            not f.endswith("_module_tests.md")]

def load_processed_prs():
    """
    Load processed PR information from JSON file.
    Returns list of dictionaries with detailed processing info.
    """
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                data = __import__("json").load(f)

                if isinstance(data, list):
                    processed_prs = []
                    for item in data:
                        if isinstance(item, dict):
                            processed_prs.append(item)
                        elif isinstance(item, int):
                            processed_prs.append({"pr_number": item, "status": "completed"})
                        elif isinstance(item, str):
                            try:
                                pr_num = int(item)
                                processed_prs.append({"pr_number": pr_num, "status": "completed"})
                            except ValueError:
                                pass
                    return processed_prs

                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"Error loading processed_prs.json: {e}")
            pass
    return []

def save_processed_prs(processed_prs):
    """
    Save processed PR information to JSON file.
    Stores detailed information about processed PRs including diff files, test files, and timestamps.
    """
    with open(PROCESSED_FILE, "w") as f:
        __import__("json").dump(processed_prs, f, indent=4)

def check_pr_processed(processed_prs, pr_number):
    """
    Check if a PR has already been processed with all test files.
    Returns True if processed, False otherwise.
    """
    for item in processed_prs:
        if isinstance(item, dict) and item.get("pr_number") == pr_number:
            # Check if test cases and module tests exist for this PR
            testcases_file = item.get("testcases_file")
            module_file = item.get("module_tests_file")
            if testcases_file and module_file:
                return True
    return False

def fetch_pr_info(repo_name, pr_number):
    github_token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed: {response.text}")
    return response.json()

def fetch_pr_diff_via_api(repo_name, pr_number, diff_file_path=None):
    """
    Fetch PR info first, then get the diff_url and download the actual diff
    """
    github_token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"

    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"}

    try:
        # First fetch PR info to get the diff_url
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            if diff_file_path and os.path.exists(diff_file_path):
                print(f"API error, using file: {response.text}")
                with open(diff_file_path, "r") as f:
                    return f.read()
            raise Exception(f"Failed to fetch PR info: {response.text}")

        pr_info = response.json()
        diff_url = pr_info.get('diff_url')

        if not diff_url:
            if diff_file_path and os.path.exists(diff_file_path):
                print(f"No diff_url in PR info, using file")
                with open(diff_file_path, "r") as f:
                    return f.read()
            raise Exception("No diff_url found in PR info")

        # Download the actual diff
        diff_response = requests.get(diff_url)

        if diff_response.status_code == 200:
            return diff_response.text
        elif diff_response.status_code == 404:
            if diff_file_path and os.path.exists(diff_file_path):
                with open(diff_file_path, "r") as f:
                    return f.read()
            raise Exception("PR not found")
        else:
            raise Exception(f"Failed to download diff: {diff_response.text}")

    except Exception as e:
        if diff_file_path and os.path.exists(diff_file_path):
            print(f"API error, using file: {e}")
            with open(diff_file_path, "r") as f:
                return f.read()
        raise

def extract_new_changes(diff_content):
    """
    Extract only the new code changes from the diff.
    Returns the latest changes without old code.
    """
    lines = diff_content.split('\n')
    new_changes = []

    # Track if we're inside a hunk (@@ block)
    in_hunk = False
    hunk_content = []

    for line in lines:
        # Start of a hunk
        if line.startswith("@@"):
            in_hunk = True
            hunk_content = [line]
            continue

        # End of hunk (next line starts with diff or file change)
        if in_hunk and (line.startswith("diff --git") or
                       line.startswith("---") or
                       line.startswith("new file mode") or
                       line.startswith("deleted file mode")):
            in_hunk = False

        # Inside hunk: extract new additions (+) and removals (-)
        if in_hunk:
            if line.startswith("+") and not line.startswith("++"):
                # New code line (strip the +)
                new_changes.append(line[1:])
            elif line.startswith("-"):
                # Removed code (ignore for test generation)
                pass
            else:
                # Context lines (keep them for context)
                new_changes.append(line)

    return "\n".join(new_changes).strip()

def save_to_markdown(content, filename, title=""):
    """
    Save content to markdown file with proper formatting
    """
    path = os.path.join(GENERATED_FOLDER, filename)

    with open(path, "w", encoding='utf-8') as f:
        f.write(f"# {title}\n")
        f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("---\n\n")
        f.write(content)

    print(f"Saved: {filename}")
    return filename

def generate_module_tests(diff_content, pr_number):
    prompt = """
You are a senior C test architect. Generate practical module tests in C code format for the provided C code diff.

PR NUMBER: """ + str(pr_number) + """

Generate 5+ practical test scenarios:
- Test setup, action steps, and expected outputs
- Include module initialization and error handling tests
- Focus on function interactions within the module
- Test boundary conditions and edge cases
- Test overflow cases for arithmetic functions
- Test NULL pointer handling
- Test division by zero for division functions

Output format: VALID C CODE using cmocka framework

/*
 * Module: [module_name]
 * Purpose: [module purpose]
 * Example: Module-Level Tests (MT) using cmocka
 *
 * Note:
 * - Separate test file (e.g., test_[module_name].c)
 * - Assumes [module].h and [module].c exist
 */

#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include "[module_name].h"

/* ---------- Test Cases ---------- */

static void test_[test_name]_valid_inputs(void **state)
{
    (void) state;
    [test code]
    assert_[assertion]([expected], [actual]);
}

static void test_[test_name]_with_negative(void **state)
{
    (void) state;
    [test code]
    assert_[assertion]([expected], [actual]);
}

/* ---------- Test Runner ---------- */

int main(void)
{
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_[test_name]_valid_inputs),
        cmocka_unit_test(test_[test_name]_with_negative),
        [more tests...]
    };

    return cmocka_run_group_tests(tests, NULL, NULL);
}
"""
    from glm_client import call_glm_4_7_flash
    return call_glm_4_7_flash(prompt + "C CODE DIFF:" + diff_content)

def get_newest_pr_diff_files():
    """
    Get the newest PR diff files from the generated_tests folder.
    Returns a list of (filename, modification_time) tuples sorted by modification time.

    IMPORTANT: Only returns .diff files, not test case or module test files.
    """
    if not os.path.exists(GENERATED_FOLDER):
        return []

    # Only get .diff files, NOT test case or module test files
    diff_files = [f for f in os.listdir(GENERATED_FOLDER)
                  if f.endswith(".diff") and
                  not f.endswith("_testcases.md") and
                  not f.endswith("_module_tests.md")]

    # Get modification times
    newest_files = []
    for diff_file in diff_files:
        file_path = os.path.join(GENERATED_FOLDER, diff_file)
        mod_time = os.path.getmtime(file_path)
        newest_files.append((diff_file, mod_time))

    # Sort by modification time (newest first)
    newest_files.sort(key=lambda x: x[1], reverse=True)

    return [file for file, _ in newest_files]


def get_pr_number(diff_file):
    """
    Extract PR number from diff file name.
    Handles formats like: pr_48.diff, pr-50.diff, pr50.diff
    Returns None if filename format is invalid.
    """
    # Remove extension first
    if diff_file.endswith('.diff'):
        diff_file = diff_file[:-5]

    # Extract number from filename
    # Try different formats
    parts = diff_file.split('_')

    if len(parts) >= 2 and parts[1].isdigit():
        return parts[1]

    # Try hyphen separator
    parts = diff_file.split('-')
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[1]

    # Try no separator (e.g., pr50.diff)
    if diff_file.isdigit():
        return diff_file

    return None


def get_latest_patches(diff_file_path):
    """
    Extract only the latest patches from a diff file.
    Reads the diff file and extracts new changes.
    """
    try:
        with open(diff_file_path, 'r', encoding='utf-8') as f:
            diff_content = f.read()
        return extract_new_changes(diff_content)
    except Exception as e:
        print(f"[ERROR] Failed to read diff file: {e}")
        return None


def remove_pr_label(repo_name, pr_number, label_name):
    """
    Remove the specified label from a PR using GitHub API
    """
    github_token = os.getenv("GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{repo_name}/issues/{pr_number}/labels/{label_name}"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"}
    
    response = requests.delete(url, headers=headers)
    
    if response.status_code == 200 or response.status_code == 204:
        print(f"[OK] Label '{label_name}' removed from PR #{pr_number}")
        return True
    elif response.status_code == 404:
        print(f"[INFO] Label '{label_name}' not found on PR #{pr_number}")
        return False
    else:
        print(f"[WARNING] Failed to remove label: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def main(repo_name=None):
    """
    Workflow:

    1. Check for newest PR diff files in generated_tests folder
    2. Extract latest patches from these diff files
    3. Use GLM 4.7 Flash to generate test cases for the latest patches
    4. Use generated test cases to generate module tests in C code (cmocka framework)
    5. Remove the PR label after test files are created

    Note: After poller.py has run and created diff files, workflow.py:
    - Identifies the newest PR diff files
    - Extracts only the latest patches from these diff files
    - Uses GLM 4.7 Flash to generate test cases
    - Generates module tests using the generated test cases
    - Automatically removes the PR label when test generation is complete
    """

    print("=" * 60)
    print("WORKFLOW: Test Case Generation")
    print("=" * 60)

    # Step 1: Check for newest PR diff files in generated_tests folder
    print("\nStep 1: Checking for newest PR diff files in generated_tests folder...")
    diff_files = get_newest_pr_diff_files()

    if not diff_files:
        print("No diff files found in generated_tests folder.")
        print("Please run poller.py first to create diff files.")
        return 0

    print(f"Found {len(diff_files)} diff file(s)")
    for diff_file in diff_files:
        print(f"  - {diff_file}")
    print()

    # Only process the newest diff file
    newest_diff = diff_files[0]
    print(f"[INFO] Processing only the newest diff file: {newest_diff}")
    print()

    # Get repo_name for label removal from .env file
    if repo_name is None:
        repo_name = os.getenv("GITHUB_REPO")

    if not repo_name:
        print("[ERROR] GITHUB_REPO not found in .env file")
        print("Please set GITHUB_REPO in your .env file (e.g., GITHUB_REPO=microsoft/vscode)")
        return 0

    print(f"[INFO] Using repository: {repo_name}")
    print()

    # Load processed PRs
    processed_prs = load_processed_prs()
    print(f"Loaded {len(processed_prs)} processed PRs from record")
    print()

    # Step 2: Extract latest patches from the newest diff file
    print("=" * 60)
    print("Step 2: Extracting latest patches from diff files...")
    print("=" * 60)

    diff_file = newest_diff
    pr_number = get_pr_number(diff_file)
    if not pr_number:
        print(f"[WARNING] Could not extract PR number from filename: {diff_file}")
        return 0

    print(f"\nProcessing: {diff_file} (PR #{pr_number})")
    print("-" * 60)

    # Extract latest patches from diff file
    diff_path = os.path.join(GENERATED_FOLDER, diff_file)
    latest_patches = get_latest_patches(diff_path)

    if not latest_patches:
        print(f"[ERROR] Failed to extract patches from {diff_file}")
        return 0

    patches_count = len(latest_patches.split('\n'))
    print(f"[OK] Extracted {patches_count} lines of latest patches")

    # Step 3: Use GLM 4.7 Flash to generate test cases for the latest patches
    print("\nStep 3: Generating test cases using GLM 4.7 Flash...")

    testcases_file = f"pr_{pr_number}_testcases.md"
    module_file_c = f"pr_{pr_number}_module_tests.c"

    # Check if files already exist
    testcases_exist = os.path.exists(testcases_file)
    module_tests_exist = os.path.exists(module_file_c)

    if testcases_exist and module_tests_exist:
        print(f"[SKIP] Files already exist for PR #{pr_number}")
        # Add to processed list if not already there
        if not check_pr_processed(processed_prs, pr_number):
            processed_prs.append({
                "pr_number": pr_number,
                "diff_file": diff_file,
                "testcases_file": testcases_file,
                "module_tests_file": module_file_c,
                "processed_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "completed"
            })
        return 0

    # Generate test cases
    try:
        print("Generating test case definitions...")
        testcases = generate_testcases(latest_patches)
        save_to_markdown(testcases, testcases_file, f"Test Cases - PR #{pr_number}")
        print(f"[OK] Test cases saved to {testcases_file}")
    except Exception as e:
        print(f"[ERROR] Failed to generate test cases: {e}")
        return 0

    # Step 4: Use generated test cases to generate module tests in C code (cmocka framework)
    print("\nStep 4: Generating module tests in C code (cmocka framework)...")

    try:
        print("Generating module tests...")
        module_tests_c = generate_module_tests(latest_patches, pr_number)
        module_file_c = f"pr_{pr_number}_module_tests.c"
        save_to_markdown(module_tests_c, module_file_c, f"Module Tests - PR #{pr_number}")
        print(f"[OK] Module tests saved to {module_file_c}")

        # Step 5: Remove the PR label after test files are created
        print("\nStep 5: Removing PR label after successful test generation...")
        label_name = os.getenv("PR_LABEL", "ai-test")
        remove_pr_label(repo_name, pr_number, label_name)

    except Exception as e:
        print(f"[ERROR] Failed to generate module tests: {e}")
        return 0

    # Add to processed list
    if os.path.exists(testcases_file) and os.path.exists(module_file_c):
        if not check_pr_processed(processed_prs, pr_number):
            processed_prs.append({
                "pr_number": pr_number,
                "diff_file": diff_file,
                "testcases_file": testcases_file,
                "module_tests_file": module_file_c,
                "processed_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "completed"
            })
            print(f"[RECORD] Added PR #{pr_number} to processed list")
        else:
            print(f"[RECORD] PR #{pr_number} already in processed list")
    else:
        print(f"[WARNING] Not adding PR #{pr_number} to processed list - incomplete files")

    # Save processed PRs
    save_processed_prs(processed_prs)

    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETE")
    print("=" * 60)
    print(f"Processed {len(processed_prs)} PR(s) total")
    print(f"Generated test cases and module tests")
    return 0


if __name__ == "__main__":
    main()
