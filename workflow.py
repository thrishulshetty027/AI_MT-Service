import os
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

llm_type = os.getenv("USE_LLM_TYPE", "vio")
cantata_integration_enabled = os.getenv("INTEGRATE_CANTATA", "true").lower() == "true"

print(f"[INFO] Using LLM type: {llm_type.upper()}")
print(f"[INFO] Cantata integration: {'ENABLED' if cantata_integration_enabled else 'DISABLED'}")

from cantata_integration import generate_cantata_tests
from testcase_generator import generate_testcases

if llm_type == "glm":
    from glm_client import call_glm_4_7_flash as call_llm
else:
    from vio_llm_client import call_vio_llm as call_llm

GENERATED_FOLDER = r"C:/Users/uik03287/Simple-File-System/generated_tests"
PROCESSED_FILE = r"C:/Users/uik03287/Simple-File-System/processed_prs.json"

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

def parse_test_cases_from_markdown(testcases_file):
    """
    Parse test case definitions from markdown file and convert to structured format
    
    Args:
        testcases_file: Path to the test cases markdown file
        
    Returns:
        List of test case dictionaries
    """
    import re
    
    test_cases = []
    
    try:
        with open(testcases_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to parse as markdown table format
        if '|' in content:
            lines = content.split('\n')
            in_table = False
            headers = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check if this is a header row (contains column names)
                if '|' in line and ('Test Case ID' in line or 'Test Scenario' in line or 'Function Name' in line):
                    headers = [h.strip() for h in line.split('|')[1:-1]]
                    in_table = True
                    continue
                    
                # Skip separator row
                if in_table and line.startswith('|---'):
                    continue
                    
                # Process data rows
                if in_table and line.startswith('|'):
                    values = [v.strip() for v in line.split('|')[1:-1]]
                    if len(values) == len(headers):
                        test_case = dict(zip(headers, values))
                        test_cases.append(test_case)
            
            # If no header found but table data exists, create default headers
            if not in_table and '|' in content:
                # Count the number of pipes to determine column count
                sample_line = [line for line in lines if '|' in line and not line.startswith('---') and not line.strip().startswith('#')][0]
                num_columns = sample_line.count('|') - 1
                headers = ['Test Case ID', 'Function Name', 'Test Scenario', 'Input Values', 'Pre-Conditions', 'Test Steps', 'Expected Result', 'Post-Conditions', 'Test Type'][:num_columns]
                
                # Reparse with default headers
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('|---'):
                        continue
                    if '|' in line:
                        values = [v.strip() for v in line.split('|')[1:-1]]
                        if len(values) == len(headers):
                            test_case = dict(zip(headers, values))
                            test_cases.append(test_case)
        
        # If no table found, try to parse function stub format
        if not test_cases:
            # Parse C function stub format
            function_pattern = r'/\*\s*\*\s*Test Case:\s*([^\n]*)\s*\*\s*Description:\s*([^\n]*)\s*\*/\s*void\s+(\w+)\([^)]*\)\s*\{([^}]+)\}'
            matches = re.finditer(function_pattern, content, re.DOTALL)
            
            for match in matches:
                scenario = match.group(1).strip()
                description = match.group(2).strip()
                function_name = match.group(3).strip()
                function_body = match.group(4).strip()
                
                # Extract test steps and expected results from comments
                test_steps = ""
                expected_result = ""
                input_values = ""
                
                # Look for TODO comments with test implementation hints
                todo_matches = re.findall(r'/\*\s*([^*]+)\*/', function_body)
                for comment in todo_matches:
                    comment = comment.strip()
                    if 'input' in comment.lower() or '=' in comment:
                        input_values = comment
                    elif 'expected' in comment.lower():
                        expected_result = comment
                    elif 'test' in comment.lower():
                        test_steps += comment + " "
                
                test_cases.append({
                    'Test Case ID': f"TC_{len(test_cases)+1:03d}",
                    'Function Name': function_name,
                    'Test Scenario': scenario or description,
                    'Input Values': input_values,
                    'Pre-Conditions': '',
                    'Test Steps': test_steps,
                    'Expected Result': expected_result,
                    'Post-Conditions': '',
                    'Test Type': 'Functional'
                })
        
        print(f"[INFO] Parsed {len(test_cases)} test cases from {testcases_file}")
        return test_cases
        
    except Exception as e:
        print(f"[ERROR] Failed to parse test cases: {e}")
        return []

def generate_module_tests(diff_content, pr_number):
    """
    Generate module tests using Cantata++ framework.
    This function is Cantata-only and does not support cmocka.
    """
    # Cantata is always enabled, no fallback to cmocka
    print("[INFO] Generating Cantata-compatible module tests")
    
    # Load and parse test cases if they exist
    testcases_file = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}_testcases.md")
    test_cases = None
    
    if os.path.exists(testcases_file):
        print(f"[INFO] Loading test cases from {testcases_file}")
        test_cases = parse_test_cases_from_markdown(testcases_file)
    
    cantata_result = generate_cantata_tests(diff_content, pr_number, test_cases)

    # Save Cantata test script
    module_name = cantata_result['module_name']
    test_script_file = f"test_{module_name}_{pr_number}.c"
    header_file = f"{module_name}.h"

    save_to_markdown(cantata_result['test_script'], test_script_file,
                    f"Cantata Test Script - PR #{pr_number}")
    save_to_markdown(cantata_result['header_file'], header_file,
                    f"Module Header - PR #{pr_number}")

    print(f"[OK] Cantata test script saved to {test_script_file}")
    print(f"[OK] Module header saved to {header_file}")

    # Return the test script content for reference
    return cantata_result['test_script']
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
    3. Use LLM to generate test case definitions in Cantata format
    4. Use Cantata++ framework to generate module tests
    5. Remove the PR label after test files are created

    Note: After poller.py has run and created diff files, workflow.py:
    - Identifies the newest PR diff files
    - Extracts only the latest patches from these diff files
    - Uses LLM to generate Cantata test case definitions
    - Generates Cantata module tests using the generated definitions
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

    # Step 3: Generate Cantata test case definitions using LLM
    print("\nStep 3: Generating Cantata test case definitions...")

    testcases_file = f"pr_{pr_number}_testcases.md"

    # Check if test case file already exists
    if os.path.exists(os.path.join(GENERATED_FOLDER, testcases_file)):
        print(f"[SKIP] Test case file already exists: {testcases_file}")
        # Add to processed list if not already there
        if not check_pr_processed(processed_prs, pr_number):
            processed_prs.append({
                "pr_number": pr_number,
                "diff_file": diff_file,
                "testcases_file": testcases_file,
                "module_tests_file": None,
                "processed_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "status": "testcases_completed"
            })
        return 0

    # Generate test cases using LLM
    try:
        print("Generating test case definitions...")
        testcases = generate_testcases(latest_patches)
        save_to_markdown(testcases, testcases_file, f"Test Cases - PR #{pr_number}")
        print(f"[OK] Test cases saved to {testcases_file}")
    except Exception as e:
        print(f"[ERROR] Failed to generate test cases: {e}")
        return 0

    # Step 4: Generate Cantata module tests
    print("\nStep 4: Generating Cantata module tests...")

    module_tests_file = f"test_module_{pr_number}.c"

    try:
        print("Generating module tests...")
        generate_module_tests(latest_patches, pr_number)

        # Step 5: Remove the PR label after test files are created
        print("\nStep 5: Removing PR label after successful test generation...")
        label_name = os.getenv("PR_LABEL", "ai-test")
        remove_pr_label(repo_name, pr_number, label_name)

    except Exception as e:
        print(f"[ERROR] Failed to generate module tests: {e}")
        return 0

    # Add to processed list
    if os.path.exists(os.path.join(GENERATED_FOLDER, testcases_file)) and os.path.exists(os.path.join(GENERATED_FOLDER, module_tests_file)):
        if not check_pr_processed(processed_prs, pr_number):
            processed_prs.append({
                "pr_number": pr_number,
                "diff_file": diff_file,
                "testcases_file": testcases_file,
                "module_tests_file": module_tests_file,
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
