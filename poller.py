import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
LABEL_NAME = os.getenv("PR_LABEL", "ai-test")

GENERATED_FOLDER = "generated_tests"
PROCESSED_FILE = "processed_prs.json"


def ensure_generated_folder():
    if not os.path.exists(GENERATED_FOLDER):
        os.makedirs(GENERATED_FOLDER)


def load_processed_prs():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as f:
            return json.load(f)
    return []


def save_processed_prs(processed_prs):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed_prs, f, indent=4)


def get_labeled_prs():
    """
    Fetch open PRs with specific label using GitHub Issues API
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
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
        print("Failed to fetch PRs:", response.text)
        return []

    issues = response.json()

    # Filter only PRs (issues API returns both issues and PRs)
    prs = [issue for issue in issues if "pull_request" in issue]

    return prs


def download_pr_diff(pr_number):
    """
    Download PR diff using Pulls API
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to download diff for PR #{pr_number}")
        return None


def save_diff(pr_number, diff_content):
    file_path = os.path.join(GENERATED_FOLDER, f"pr_{pr_number}.diff")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(diff_content)
    print(f"Saved diff to {file_path}")


def main():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("Missing GITHUB_TOKEN or GITHUB_REPO in .env")
        return

    ensure_generated_folder()

    processed_prs = load_processed_prs()
    prs = get_labeled_prs()

    if not prs:
        print("ℹNo labeled PRs found.")
        return

    for pr in prs:
        pr_number = pr["number"]

        if pr_number in processed_prs:
            print(f"⏭PR #{pr_number} already processed. Skipping.")
            continue

        print(f"Processing PR #{pr_number}")

        diff_content = download_pr_diff(pr_number)

        if diff_content:
            save_diff(pr_number, diff_content)
            processed_prs.append(pr_number)

    save_processed_prs(processed_prs)
    print("Polling complete.")


if __name__ == "__main__":
    main()
