import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

llm_type = os.getenv("USE_LLM_TYPE", "vio")

print(f"[INFO] Using LLM type: {llm_type.upper()}")

if llm_type == "glm":
    from glm_client import call_glm_4_7_flash as call_llm
    print("[INFO] Will use GLM (opencode CLI)")
else:
    from vio_llm_client import call_vio_llm as call_llm
    print("[INFO] Will use VIO LLM")

# =====================================================
# CANTATA TEST CASE GENERATOR
# =====================================================

SYSTEM_PROMPT = """
You are a senior C test architect.

TASK:
Generate module-level TEST CASE DEFINITIONS for the provided C code diff
aligned with Cantata++ framework semantics, but represented ONLY as a markdown table.

STRICT RULES (MANDATORY):

* Output MUST start with the table header row
* Output MUST include the separator row with dashes after the header
* Output ONLY a markdown table.
* DO NOT generate actual C code.
* DO NOT include cmocka.
* DO NOT include explanations or prose.
* DO NOT include code blocks.
* Extract function names ONLY from the diff.
* If no function is found, output an empty table.

FORMAT RULES:

* The response MUST strictly follow this pattern (EXACTLY, including the header):

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |
| ------------ | ------------- | ------------- | ------------ | -------------- | ---------- | --------------- | --------------- | --------- |
| TC_001       | ...           | ...           | ...          | ...            | ...        | ...             | ...             | ...       |
| TC_002       | ...           | ...           | ...          | ...            | ...        | ...             | ...             | ...       |

* The first row MUST be the table header (Test Case ID, Function Name, etc.)
* The second row MUST be the separator row with dashes (------------)
* The third row onwards MUST be test case data rows

* Each test case MUST be on a separate line.

* You MUST insert a newline after every row.

* NEVER place two test cases on the same line.

* NEVER continue a row without closing it with a "|" character.

* Each row MUST contain EXACTLY 9 columns.

* Count "|" characters — each row MUST have 10 pipe symbols.

* If formatting is violated, REGENERATE the entire output.

* DO NOT output paragraphs under any circumstance.

* DO NOT compress rows into a single line.

* DO NOT wrap the table in code blocks.

* DO NOT generate continuous text

* EACH row MUST start with | and end with |

* Use TC_001, TC_002...

CRITICAL REMINDER:

* ALWAYS include the table header row at the very beginning
* ALWAYS include the separator row with dashes (| ------------ |) after the header
* Then list all test case data rows

CELL FORMATTING RULE (CRITICAL):

* Each table cell MUST be a SINGLE LINE.
* DO NOT use line breaks inside any cell.
* Replace line breaks with " ; " separator.

Example:

CORRECT:
TEST_SCRIPT_INFO: Init ; TEST CASE: Call func ; Function call: func(x) ; Coverage: branch

WRONG:
TEST_SCRIPT_INFO: Init
TEST CASE: Call func
Function call: func(x)

* Test Steps and Expected Result MUST be written in a single line using separators like " ; "
* DO NOT press Enter inside a row


CANTATA ALIGNMENT (MANDATORY):

* Test Steps MUST include:

  * TEST_SCRIPT_INFO
  * TEST CASE execution
  * Function call
  * Coverage intent

* Expected Result MUST include:

  * CHECK statements
  * Expected outputs / return values

TEST DESIGN COVERAGE:

* Normal cases
* Edge cases
* Boundary values
* Invalid inputs
* All branches

VALIDATION:

* Output MUST include the table header row
* Output MUST include the separator row with dashes
* Output ONLY the table
* Ensure proper line breaks between rows
* Regenerate if formatting is incorrect

  """

# =====================================================
# GENERATOR FUNCTION
# =====================================================

def generate_testcases(diff_text):
    """
    Generates structured Cantata test case definitions
    from C code diff input.
    """

    # Prevent timeout with large diffs
    MAX_DIFF_SIZE = 100000
    diff_text = diff_text[:MAX_DIFF_SIZE]

    prompt = SYSTEM_PROMPT + "\n\nC CODE DIFF:\n" + diff_text

    response = call_llm(prompt)

    return clean_output(response)


# =====================================================
# OUTPUT CLEANER
# =====================================================

def clean_output(text):
    """
    Removes accidental explanations or code blocks.
    Keeps only Cantata test case definitions.
    """
    # Remove markdown code blocks if present
    text = re.sub(r'```markdown\n?', '', text)
    text = re.sub(r'```\n?', '', text)

    lines = text.splitlines()
    cleaned = []
    inside_c_code = False

    for line in lines:
        # Check if we're starting C code block
        if '/*' in line or 'void' in line or 'TEST_SCRIPT' in line:
            inside_c_code = True
            cleaned.append(line)

        # Check if we're ending C code block
        elif '*/' in line or (inside_c_code and '*/' in line):
            cleaned.append(line)
            inside_c_code = False

        # Inside C code block, keep the content
        elif inside_c_code:
            cleaned.append(line)

        # Skip non-C code lines
        elif not line.strip():
            continue
        elif line.strip().startswith('#'):
            continue
        elif line.strip().startswith('```'):
            continue

        # Keep empty lines for formatting
        elif line.strip() == '':
            if cleaned and cleaned[-1].strip():
                cleaned.append(line)

    return "\n".join(cleaned).strip()


# =====================================================
# EXAMPLE USAGE
# =====================================================

if __name__ == "__main__":
    print("Cantata Test Case Generator")
    print("=" * 60)
    print("\nThis module generates Cantata-compatible test case definitions.")
    print("\nKey Functions:")
    print("  - generate_testcases() : Generate Cantata test case definitions")
    print("  - clean_output() : Clean LLM output to remove extraneous content")
