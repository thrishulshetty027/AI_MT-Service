import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
LABEL_NAME = os.getenv("PR_LABEL", "ai-test")

GENERATED_FOLDER = "generated_tests"
PROCESSED_FILE = "processed_prs.json"


def ensure_generated_folder():
    if not os.path.exists(GENERATED_FOLDER):
        os.makedirs(GENERATED_FOLDER)


def load_processed_prs():
    """
    Safely load processed PR numbers.
    Supports:
    - List format: [23, 24]
    - Dict format: {"processed": [23, 24]}
    """
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                data = json.load(f)

                if isinstance(data, list):
                    return data

                if isinstance(data, dict) and "processed" in data:
                    return data["processed"]

        except json.JSONDecodeError:
            print("processed_prs.json corrupted. Resetting.")
            return []

    return []


def save_processed_prs(processed_prs):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed_prs, f, indent=4)


def generate_and_post_testcases(pr_number, repo_name, diff_content):
    """
    Generate test cases using GLM 4.7 Flash and post as a comment on the PR
    NOTE: This function is no longer used. Test generation is now handled by workflow.py
    """
    return True


def post_pr_comment(pr_number, repo_name, comment_text):
    """
    Post a comment on the PR using GitHub API
    """
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}/comments"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    }

    data = {
        "body": f"## AI-Generated Test Cases\n\n{comment_text}"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code != 201:
        print(f"Failed to post comment on PR #{pr_number} in {repo_name}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        return False

    print("Comment posted successfully")
    return True


def get_labeled_prs(repo_name):
    """
    Fetch open PRs with specific label using GitHub Issues API
    """
    url = f"https://api.github.com/repos/{repo_name}/issues"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    params = {
        "state": "open",
        "labels": LABEL_NAME
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print("Failed to fetch PRs:")
        print(response.text)
        return []

    issues = response.json()

    # Issues API returns both issues and PRs - filter only PRs
    prs = [issue for issue in issues if "pull_request" in issue]

    return prs


def download_pr_diff_alt(repo_name, pr_number):
    """
    Download only the latest diff for the PR
    Fetches PR info first to get the diff_url, then downloads the actual diff
    """
    url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    print(f"Fetching PR info for PR #{pr_number}")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch PR info for PR #{pr_number}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        return None

    pr_info = response.json()
    diff_url = pr_info.get('diff_url')

    if not diff_url:
        print(f"No diff_url found in PR info for PR #{pr_number}")
        return None

    print(f"Downloading diff from: {diff_url}")
    diff_response = requests.get(diff_url)

    if diff_response.status_code != 200:
        print(f"Failed to download diff from {diff_url}")
        print(f"Status: {diff_response.status_code}")
        print(f"Response: {diff_response.text}")
        return None

    diff_content = diff_response.text
    print(f"Downloaded {len(diff_content)} bytes")
    return diff_content


def save_diff(pr_number, repo_name, diff_content):
    # Use short filename: pr_{number}.diff
    file_path = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}.diff")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(diff_content)

    print(f"Saved diff to {file_path}")


def parse_github_url(url):
    """
    Parse GitHub URL to extract owner/repo name
    """
    if not url:
        return None

    url = url.strip()

    if url.endswith('.git'):
        url = url[:-4]

    import re
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', url)

    if match:
        owner = match.group(1)
        repo = match.group(2)
        return f"{owner}/{repo}"

    return None


def get_repo_name():
    """
    Ask user for GitHub repository URL and parse it
    """
    print("\n" + "="*60)
    print("AI Test Case Generator - Multi-Repository Poller")
    print("="*60)
    
    while True:
        print("\nEnter GitHub repository URL")
        print("   Examples:")
        print("   - https://github.com/microsoft/vscode")
        print("   - https://github.com/thrishulshetty027/Simple-File-System.git")
        print("\nPaste your repo URL:")
        
        repo_url = input("> ").strip()
        
        if not repo_url:
            print("Repository URL cannot be empty!")
            continue
        
        repo_name = parse_github_url(repo_url)
        
        if not repo_name:
            print("Invalid GitHub URL format!")
            print("   Please use: https://github.com/owner/repo or https://github.com/owner/repo.git")
            continue
        
        print(f"OK Parsed repository: {repo_name}")
        print(f"Searching for PRs with '{LABEL_NAME}' label in {repo_name}...")
        return repo_name


def main():
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN not found in .env file")
        return

    print(f"Using {os.getenv('MODEL_NAME', 'VIO:GPT-5-medium')} model")
    
    repo_name = get_repo_name()
    
    ensure_generated_folder()

    processed_prs = load_processed_prs()
    prs = get_labeled_prs(repo_name)

    if not prs:
        print(f"No labeled PRs found in {repo_name}")
        return

    for pr in prs:
        pr_number = pr["number"]
        
        if pr_number in processed_prs:
            print(f"PR #{pr_number} already processed. Skipping.")
            continue

        print(f"\n{'='*60}")
        print(f"Processing NEW PR #{pr_number} from {repo_name}")
        print(f"{'='*60}")

        diff_content = download_pr_diff_alt(repo_name, pr_number)

        if diff_content:
            save_diff(pr_number, repo_name, diff_content)
            processed_prs.append(pr_number)

            generate_and_post_testcases(pr_number, repo_name, diff_content)

            print(f"\n{'='*60}")
            print(f"PR #{pr_number} fully processed")
            print(f"{'='*60}")
            print(f"\nPolling complete. Exiting after one PR.")
            break

    save_processed_prs(processed_prs)

    if not processed_prs:
        print("No new PRs to process.")


if __name__ == "__main__":
    main()
