import re
from glm_client import call_glm_4_7_flash

# =====================================================
# STRICT SYSTEM PROMPT
# =====================================================

SYSTEM_PROMPT = """
You are a senior C unit test architect.

TASK:
Generate module-level TEST CASE DEFINITIONS for the provided C code diff.

STRICT RULES (MANDATORY):

* Use cmocka-style unit test design principles.
* DO NOT generate compilable C test code.
* DO NOT generate cmocka test function implementations.
* DO NOT explain anything.
* DO NOT summarize the diff.
* DO NOT describe the framework.
* DO NOT include prose or paragraphs.
* Output ONLY structured Markdown tables.
* If you generate explanations or C code, the output is INVALID.

MARKDOWN TABLE STRUCTURE (MANDATORY):

* Each table MUST contain exactly 9 columns.
* Column headers MUST match EXACTLY and in this order:

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |
| ------------ | ------------- | ------------- | ------------ | -------------- | ---------- | --------------- | --------------- | --------- |

* The header separator row using `---` is REQUIRED.
* The separator row MUST appear immediately after the header row.
* Every row MUST:

  * Start with a pipe `|`
  * End with a pipe `|`
  * Contain exactly 9 pipe-separated columns
  * Contain exactly one space before and after each cell content
* No extra spaces before the first pipe.
* No extra spaces after the last pipe.
* No missing pipes.
* No merged columns.
* No multi-line cells.
* No blank lines inside or between tables.
* The table must render correctly in GitHub Markdown.
* Output must be visually aligned when rendered.

FOR EACH modified or newly added function:

Create a Markdown table with exactly 9 columns in this exact format:

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |

COVER ALL:

* Normal behavior
* Boundary conditions
* Invalid inputs
* NULL pointer handling
* Error handling paths
* Overflow cases (if relevant)

Each function must have multiple test cases.
Test Case IDs must be unique (TC_001, TC_002, etc).
Test Case IDs must increment sequentially across all functions without resetting.
Do NOT skip any test case IDs.

OUTPUT ORDERING RULES (MANDATORY):

1. Generate test cases ALPHABETICALLY by Function Name
2. Within each function, generate test cases in numerical order
3. Group test cases by Function Name
4. Continue numbering from the last Test Case ID without resetting

VALIDATION REQUIREMENT:

* If any formatting rule is violated, regenerate the entire output until all constraints are satisfied.
* Output ONLY tables.
* DO NOT use markdown code blocks.
* DO NOT use backticks around the table.
* DO NOT add any text before or after the tables.

"""

# =====================================================
# GENERATOR FUNCTION
# =====================================================

def generate_testcases(diff_text):
    """
    Generates structured cmocka-style test case tables
    from C code diff input.
    """

    # Prevent timeout with large diffs
    MAX_DIFF_SIZE = 100000
    diff_text = diff_text[:MAX_DIFF_SIZE]

    prompt = SYSTEM_PROMPT + "\n\nC CODE DIFF:\n" + diff_text

    response = call_glm_4_7_flash(prompt)

    return clean_output(response)


# =====================================================
# OUTPUT CLEANER (prevents model misbehavior)
# =====================================================

def clean_output(text):
    """
    Removes accidental explanations or code blocks.
    Keeps only Markdown tables.
    """
    # Remove markdown code blocks if present
    text = re.sub(r'```markdown\n?', '', text)
    text = re.sub(r'```\n?', '', text)

    lines = text.splitlines()
    cleaned = []
    inside_table = False

    for line in lines:
        # Skip lines that are not part of tables
        if not line.strip().startswith("|"):
            if inside_table:
                # If we were in a table and hit non-table content, stop
                break
            continue

        # Process table lines
        if line.strip().startswith("|"):
            inside_table = True
            cleaned.append(line)
        elif inside_table and line.strip() == "":
            # Keep empty lines within tables for formatting
            cleaned.append(line)
        elif inside_table:
            # Stop if model starts writing explanations
            break

    return "\n".join(cleaned).strip()