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
# PROMPT 1: TEST CASE GENERATION
# =====================================================

PROMPT_1 = """
You are a senior C test architect specializing in Cantata++.

TASK:
Generate module-level TEST CASE DEFINITIONS for the provided C code diff as a markdown table.

========================================
CORE PRINCIPLE: DATA-FIRST TEST DESIGN
========================================

You MUST generate realistic and meaningful test data.
Do NOT use default values like 0 unless explicitly required.
Each test case MUST use distinct and meaningful values.

Examples:
- Arrays -> {10,5,8,2,7}
- Integers -> 1, -1, 100, boundary values
- Sizes -> valid sizes (not 0 unless testing invalid case)

========================================
CRITICAL RULES
========================================

1. All variables used in Test Steps MUST be declared in Input Values
2. All statements MUST end with semicolons
3. Function calls MUST match exact signature from diff
4. No undeclared variables
5. No generic variable names:
   Not allowed: s, h, v, e, r, n
   Allowed: queue_var, input_value, expected_result
6. No void return assignments
7. No invalid pointer usage

========================================
STRUCT HANDLING
========================================

If function uses:

Queue:
struct Queue { int front; int rear; int capacity; int items[MAX_SIZE]; }

Stack:
struct Stack { int top; int capacity; int* items; }

Node:
struct Node { int data; struct Node* next; }

========================================
INPUT VALUE RULES
========================================

- All parameters MUST be declared
- All values MUST be initialized
- Use real test values (not zeros everywhere)

Examples:
"array_input={10,5,8,2,7}, size_value=5"
"input_value=10, expected_result=1"

========================================
TEST STEP FORMAT
========================================

"TEST_SCRIPT_INFO: description ; TEST CASE: func ; Function call: func(param_list) ; Coverage: type"

Valid:
func(array_input, size_value)

Invalid:
func(array_input[], size_value)

========================================
EXPECTED RESULT FORMAT
========================================

"CHECK: return_value == expected_result"

========================================
OUTPUT FORMAT
========================================

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |
| ------------ | ------------- | ------------- | ------------ | -------------- | ---------- | --------------- | --------------- | --------- |

- Exactly 10 pipe symbols per row
- No extra text
- Only markdown table

========================================
TEST COVERAGE REQUIREMENTS
========================================

Generate test cases for:
- Normal case
- Edge case
- Boundary values
- Invalid inputs
- Minimum and maximum values

========================================
FINAL VALIDATION
========================================

Before output:
- No missing variables
- No zero-only test data
- All parameters used correctly
- Function calls valid
- Table format correct

If any rule is violated, regenerate completely.

========================================
GOAL
========================================

Produce test cases that:
- Are meaningful
- Use real values
- Can be converted into valid C tests
- Cover all logical branches
"""

# =====================================================
# PROMPT 2: MODULE TEST CODE GENERATION
# =====================================================

PROMPT_2 = """
You are a C test code generator for Cantata++.

TASK:
Convert structured test cases into valid C module test code.

========================================
INPUT
========================================

- Function signature
- Test cases (derived from markdown table)

========================================
STRICT RULES
========================================

1. Use exact input values from test cases
   Do not replace values with defaults like 0

2. Array syntax:
   Valid: int arr[] = {1,2,3};
   Invalid: int arr[] = [1,2,3];
   Invalid: int arr[] = 0;

3. Function calls:
   Valid: func(arr, size);
   Invalid: func(arr[], size);

4. Return type handling:
   If return type is int:
       declare result variable and assert
   If return type is void:
       call function and validate state (do not assign result)

5. All variables must be declared before use

6. No unknown types allowed

7. No undeclared variables

8. Code must compile in standard C

========================================
VARIABLE RULES
========================================

- Arrays must be initialized with braces {}
- Pointers must be properly declared
- Structs must be defined before use
- Use descriptive variable names

========================================
ASSERTION RULES
========================================

- Use ASSERT_EQUALS(expected, actual) for return values
- For void functions, validate state changes

========================================
OUTPUT REQUIREMENTS
========================================

- Only valid C code
- No explanations
- No markdown
- No extra text

========================================
VALIDATION BEFORE OUTPUT
========================================

Ensure:
- No invalid array syntax
- No incorrect function calls
- No missing declarations
- No "unknown" types
- All test values correctly used

If any issue exists, fix before output.

========================================
GOAL
========================================

Generate fully valid, compilable Cantata-compatible C test code using the provided test cases.
"""

# =====================================================
# GENERATOR FUNCTIONS
# =====================================================

def generate_testcases(diff_text):
    """
    Stage 1: Generates structured Cantata test case definitions (Markdown Table).
    Uses the high-fidelity PROMPT_1.
    """
    MAX_DIFF_SIZE = 100000
    diff_text = diff_text[:MAX_DIFF_SIZE]

    prompt = PROMPT_1 + "\n\nC CODE DIFF:\n" + diff_text
    response = call_llm(prompt)
    return clean_output(response)

def generate_module_test_code(function_signature, test_cases_markdown):
    """
    Stage 2: Converts structured test cases into C module test code.
    Uses the strict PROMPT_2.
    """
    prompt = f"{PROMPT_2}\n\nFUNCTION SIGNATURE:\n{function_signature}\n\nTEST CASES:\n{test_cases_markdown}"
    response = call_llm(prompt)
    return clean_output(response)

def generate_cantata_tests(diff_content, pr_number, test_cases):
    """
    Main function that orchestrates both stages.
    
    Args:
        diff_content: C code diff
        pr_number: PR number for naming
        test_cases: Parsed test case data from markdown file
        
    Returns:
        Dictionary with module_name, test_script, header_file
    """
    # Generate test case markdown first (Stage 1)
    print("[INFO] Stage 1: Generating test case definitions (high-fidelity)...")
    testcases_markdown = generate_testcases(diff_content)
    
    # Save test cases
    generated_folder = "generated_tests"
    testcases_file = os.path.join(generated_folder, f"pr_{pr_number}_testcases.md")
    with open(testcases_file, "w") as f:
        f.write(testcases_markdown)
    print(f"[OK] Test cases saved to {testcases_file}")
    
    # Generate C code from test cases (Stage 2)
    print("[INFO] Stage 2: Generating C module test code (strict rules)...")
    
    # Extract function signatures from diff
    func_signatures = []
    
    # Find function signatures in diff
    signature_pattern = r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{'
    matches = re.findall(signature_pattern, diff_content)
    for match in matches:
        ret_type, func_name, params = match
        param_list = []
        if params.strip():
            for p in params.split(','):
                p = p.strip()
                if ':' in p:  # Handle pointer types like int* arr
                    p_type, p_name = p.split(':')
                    param_list.append({"name": p_name.strip(), "type": p_type.strip()})
                else:  # Handle simple types like int a
                    param_list.append({"name": p, "type": "int"})
        func_signatures.append({
            "function_name": func_name,
            "return_type": ret_type,
            "parameters": param_list
        })
    
    print(f"[INFO] Extracted {len(func_signatures)} function signatures")
    
    # Generate C code for each function using the markdown table
    all_test_code = ""
    
    for func in func_signatures:
        print(f"[INFO] Generating C code for function: {func['function_name']}")
        
        # Build the prompt with function signature and test cases
        code_prompt = f"{PROMPT_2}\n\nFUNCTION SIGNATURE:\n{func}\n\nTEST CASES:\n{testcases_markdown}"
        
        # Call LLM to generate C code
        c_code = call_llm(code_prompt)
        
        # Clean the output
        c_code = clean_output(c_code)
        
        # Append to the total code
        if all_test_code:
            all_test_code += "\n\n"
        all_test_code += c_code
    
    # Return results
    module_name = f"module_{pr_number}"
    
    return {
        "module_name": module_name,
        "test_script": all_test_code,
        "header_file": f"// Header for module {module_name}"
    }

# =====================================================
# OUTPUT CLEANER
# =====================================================

def clean_output(text):
    """
    Removes accidental explanations, markdown blocks, or prose.
    """
    # Remove markdown code blocks
    text = re.sub(r'```markdown\n?', '', text)
    text = re.sub(r'```c\n?', '', text)
    text = re.sub(r'```\n?', '', text)

    lines = text.splitlines()
    cleaned = []
    
    # Basic filtering to remove common LLM conversational filler
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(("here is", "sure", "certainly", "below is", "the generated")):
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()

# =====================================================
# EXAMPLE USAGE
# =====================================================

if __name__ == "__main__":
    print("Cantata Two-Stage Test Generator")
    print("=" * 60)
    
    sample_diff = "int add(int a, int b) { return a + b; }"
    
    print("\n--- Stage 1: Generating Test Cases ---")
    tcs = generate_testcases(sample_diff)
    print(tcs)
    
    print("\n--- Stage 2: Generating C Code ---")
    code = generate_module_test_code("int add(int a, int b)", tcs)
    print(code)
