import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("TARGET_REPO")  # format: owner/repo

if not GITHUB_TOKEN:
    raise Exception("GITHUB_TOKEN not set in .env")

if not REPO:
    raise Exception("TARGET_REPO not set in .env")

# Always anchor paths to this script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_FOLDER = os.path.join(BASE_DIR, "generated_tests")
DIFF_FILE = os.path.join(GENERATED_FOLDER, "pr_diff.txt")

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}


def get_latest_pr():
    url = f"https://api.github.com/repos/{REPO}/pulls"
    params = {
        "state": "open",
        "sort": "created",
        "direction": "desc",
        "per_page": 1
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    prs = response.json()
    return prs[0] if prs else None


def download_diff(pr):
    pr_number = pr["number"]
    diff_url = pr["diff_url"]

    response = requests.get(diff_url, headers=headers)
    response.raise_for_status()

    with open(DIFF_FILE, "w", encoding="utf-8") as f:
        f.write(response.text)

    print(f"Diff for PR #{pr_number} saved to:")
    print(f"   {DIFF_FILE}")


def main():
    print("Running poller (single execution mode)...")

    if not os.path.isdir(GENERATED_FOLDER):
        raise Exception("generated_tests folder does not exist")

    pr = get_latest_pr()

    if not pr:
        print("No open PRs found.")
        return

    print(f"Processing PR #{pr['number']}")

    download_diff(pr)

    print("Poller finished successfully.")


if __name__ == "__main__":
    main()
