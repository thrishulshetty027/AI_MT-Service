from ollama_client import call_ollama

# =====================================================
# STRICT SYSTEM PROMPT
# =====================================================

SYSTEM_PROMPT = """
You are a senior C unit test architect.

TASK:
Generate module-level TEST CASE DEFINITIONS for the provided C code diff.

STRICT RULES (MANDATORY):
- Use cmocka-style unit test design principles.
- DO NOT generate compilable C test code.
- DO NOT generate cmocka test function implementations.
- DO NOT explain anything.
- DO NOT summarize the diff.
- DO NOT describe the framework.
- DO NOT include prose or paragraphs.
- Output ONLY structured Markdown tables.
- If you generate explanations or C code, the output is INVALID.

FOR EACH modified or newly added function:

Create a Markdown table with columns:

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |

COVER ALL:
- Normal behavior
- Boundary conditions
- Invalid inputs
- NULL pointer handling
- Error handling paths
- Overflow cases (if relevant)

Each function must have multiple test cases.
Test Case IDs must be unique (TC_001, TC_002, etc).

Output ONLY tables.
No text before or after.
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
    MAX_DIFF_SIZE = 8000
    diff_text = diff_text[:MAX_DIFF_SIZE]

    prompt = SYSTEM_PROMPT + "\n\nC CODE DIFF:\n" + diff_text

    response = call_ollama(prompt)

    return clean_output(response)


# =====================================================
# OUTPUT CLEANER (prevents model misbehavior)
# =====================================================

def clean_output(text):
    """
    Removes accidental explanations or code blocks.
    Keeps only Markdown tables.
    """

    lines = text.splitlines()
    cleaned = []
    inside_table = False

    for line in lines:
        if line.strip().startswith("|"):
            inside_table = True
            cleaned.append(line)
        elif inside_table and line.strip() == "":
            cleaned.append(line)
        elif inside_table:
            # stop if model starts writing explanations
            break

    return "\n".join(cleaned).strip()