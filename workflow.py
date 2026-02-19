import os
from testcase_generator import generate_testcases

DIFF_FILE = "generated_tests/pr_diff.txt"
OUTPUT_FILE = "generated_tests/module_testcases.md"


def run():
    if not os.path.exists(DIFF_FILE):
        print("Diff file not found.")
        return

    with open(DIFF_FILE, "r", encoding="utf-8") as f:
        diff = f.read().strip()

    if not diff:
        print("⚠ Diff file empty.")
        return

    print("Generating module test cases...")

    try:
        testcases = generate_testcases(diff)

        if not testcases.strip():
            print("⚠ Empty response from generator.")
            return

        os.makedirs("generated_tests", exist_ok=True)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(testcases)

        print(f"Test cases saved to {OUTPUT_FILE}")

    except Exception as e:
        print("Workflow failed:", str(e))


if __name__ == "__main__":
    run()
