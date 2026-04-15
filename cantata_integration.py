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
# CANTATA INTEGRATION MODULE
# =====================================================

def extract_function_signatures_from_diff(diff_content):
    """
    Extract function signatures from C code diff
    Handles both standard C code and diff format with +/− prefixes
    
    Args:
        diff_content: The C code diff content
        
    Returns:
        Dictionary mapping function names to their signatures
    """
    import re
    signatures = {}
    
    # First, clean the diff content by removing diff prefixes and markers
    clean_content = diff_content
    clean_content = re.sub(r'^[\+\-]\s*', '', clean_content, flags=re.MULTILINE)
    clean_content = re.sub(r'^@@.*?@@\s*', '', clean_content, flags=re.MULTILINE)
    clean_content = re.sub(r'^(diff|index|\-\-\-|\+\+\+).*$', '', clean_content, flags=re.MULTILINE)
    
    # Match function definitions with various patterns
    patterns = [
        r'(?:int|float|double|char|void|FILE\*|struct\s+\w+)\s+(\w+)\s*\([^)]*\)\s*\{',  # Standard function
        r'(?:int|float|double|char|void|FILE\*|struct\s+\w+)\s+(\w+)\s*\([^)]*\)\s*;',  # Function declaration
        r'^\s*(?:int|float|double|char|void)\s+(\w+)\s*\([^)]*\)\s*\{',  # Function at start of line
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, clean_content, re.MULTILINE)
        for match in matches:
            signature = match.group(0).strip()
            func_name = match.group(1)
            # Skip main function
            if func_name != 'main':
                signatures[func_name] = signature
    
    # If no signatures found, try to extract from diff format directly
    if not signatures:
        # Pattern to match functions in diff format with +/−
        diff_pattern = r'[\+\-]\s*(?:int|float|double|char|void)\s+(\w+)\s*\([^)]*)\s*\{'
        matches = re.finditer(diff_pattern, diff_content, re.MULTILINE)
        for match in matches:
            # Extract function definition from diff line
            func_def = match.group(0)
            # Clean the diff prefix
            func_def = re.sub(r'^[\+\-]\s*', '', func_def)
            # Extract function name
            func_match = re.search(r'(?:int|float|double|char|void)\s+(\w+)\s*\([^)]*)\s*\{', func_def)
            if func_match:
                func_name = func_match.group(1)
                if func_name != 'main':
                    signatures[func_name] = func_def
    
    return signatures

def convert_to_cantata_format(test_cases, pr_number, module_name, function_signatures=None):
    """
    Convert AI-generated test cases to Cantata test script format
    
    Args:
        test_cases: List of test case dictionaries or raw markdown content
        pr_number: PR number for naming
        module_name: Name of the module being tested
        function_signatures: Dictionary of function signatures from C code analysis
        
    Returns:
        Formatted Cantata test script
    """

    # Set default function signatures if not provided
    if function_signatures is None:
        function_signatures = {"function_under_test": "int function_under_test(int param)"}

    # Generate extern function declarations from signatures
    extern_declarations = ""
    for func_name, signature in function_signatures.items():
        if func_name != 'function_under_test':  # Skip the generic placeholder
            extern_declarations += f"{signature};\n"
    
    # Ensure we have at least the generic function under test
    if 'function_under_test' not in function_signatures:
        extern_declarations += "extern int function_under_test(int param);\n"
    
    # Generate test functions from test cases
    test_functions = []

    # Create unique test function names based on test cases
    test_count = 1
    if test_cases:  # Check if test_cases is not None
        for test_case in test_cases:
            if isinstance(test_case, dict):
                function_name = f"test_{module_name.replace('_', '')}_{test_count}"
                scenario = test_case.get('Test Scenario', 'test_case')
                test_functions.append({
                    'name': function_name,
                    'function': f"{function_name}",
                    'scenario': scenario,
                    'input': test_case.get('Input Values', ''),
                    'expected': test_case.get('Expected Result', ''),
                    'steps': test_case.get('Test Steps', ''),
                    'function_name': test_case.get('Function Name', '')  # Preserve original function name
                })
                test_count += 1
            elif isinstance(test_case, str):
                # Handle raw string content
                test_functions.append({
                    'name': f"test_{module_name.replace('_', '')}_{test_count}",
                    'function': f"test_{module_name.replace('_', '')}_{test_count}",
                    'scenario': test_case[:50],  # First 50 chars
                    'input': '',
                    'expected': '',
                    'steps': '',
                    'function_name': ''  # No function name for string cases
                })
                test_count += 1

    # If test_cases is None or empty, create default test functions
    if not test_functions:
        for i in range(1, 4):
            test_functions.append({
                'name': f"test_{module_name.replace('_', '')}_{i}",
                'function': f"test_{module_name.replace('_', '')}_{i}",
                'scenario': f"Test case {i}",
                'input': '',
                'expected': '',
                'steps': '',
                'function_name': ''  # No function name for string cases
            })
        test_count = 4
    else:
        test_count = len(test_functions) + 1
    
    # Generate the test script
    cantata_script = f"""/*****************************************************************************
 *                          Cantata Test Script                              *
 *****************************************************************************/
/*
 *    Filename: test_{module_name}_{pr_number}.c
 *    Generated from: pr_diff_{pr_number}
 *    Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 *
 *    AI-generated test cases for PR #{pr_number}
 *****************************************************************************/
/* Environment Definition                                                    */
/*****************************************************************************/

#define TEST_SCRIPT_GENERATOR 2

/* Include files from software under test */
#include "module_{pr_number}.h"

#include <cantpp.h>  /* Cantata++ Directives */

/* pragma ipl cantata++ testscript start */

/* Global Functions */
{extern_declarations}

/* Global data */
/* None */

/* Expected variables for global data */
/* None */

/* This function initialises global data to default values. This function       */
/* is called by every test case so must not contain test case specific settings */
static void initialise_global_data(){{
    TEST_SCRIPT_WARNING("Verify initialise_global_data()\\n");
    /* No global data */
}}

/* This function copies the global data settings into expected variables for */
/* use in check_global_data(). It is called by every test case so must not   */
/* contain test case specific settings.                                      */
static void initialise_expected_global_data(){{
    TEST_SCRIPT_WARNING("Verify initialise_expected_global_data()\\n");
    /* No global data */
}}

/* This function checks global data against the expected values. */
static void check_global_data(){{
    TEST_SCRIPT_WARNING("Verify check_global_data()\\n");
    /* No global data */
}}

/* Prototypes for test functions */
void run_tests();
"""

    # Add test functions with actual implementations
    for i, test_func in enumerate(test_functions, 1):
        # Generate actual test implementation based on test case info, passing function signatures
        test_implementation = generate_test_implementation(test_func, i, function_signatures)
        cantata_script += f"""
/*****************************************************************************/
/* Test Case {i}: {test_func['scenario']}                                                 */
/*****************************************************************************/
void {test_func['function']}()
{{
    TEST_SCRIPT_INFO("Executing test: {test_func['scenario']}\\n");
    
{test_implementation}
    
    TEST_SCRIPT_INFO("Test case {i} completed\\n");
}}
"""

    # Add test runner
    # Generate test function calls dynamically
    test_calls = "\n".join([f"    {test_func['name']}();" for test_func in test_functions])
    
    cantata_script += f"""
/*****************************************************************************/
/* Coverage Analysis                                                         */
/*****************************************************************************/
/* Coverage Rule Set: 100% Entry Point + Statement + Call + Decision Coverage */
static void rule_set(char* cppca_sut,
                     char* cppca_context)
{{
#ifdef CANTPP_SUBSET_DEFERRED_ANALYSIS
    TEST_SCRIPT_WARNING("Coverage Rule Set ignored in deferred analysis mode\\n");
#elif CANTPP_INSTRUMENTATION_DISABLED
    TEST_SCRIPT_WARNING("Instrumentation has been disabled\\n");
#else
    ANALYSIS_CHECK("100% Entry Point Coverage",
                   cppca_entrypoint_cov,
                   100.0);

    ANALYSIS_CHECK("100% Statement Coverage",
                   cppca_statement_cov,
                   100.0);

    ANALYSIS_CHECK("100% Call Return Coverage",
                   cppca_callreturn_cov,
                   100.0);

    ANALYSIS_CHECK("100% Decision Coverage",
                   cppca_decision_cov,
                   100.0);

    REPORT_COVERAGE(cppca_entrypoint_cov|
                    cppca_statement_cov|
                    cppca_callreturn_cov|
                    cppca_decision_cov,
                    cppca_sut,
                    cppca_all_details|cppca_include_catch,
                    cppca_context);
#endif
}}
/*****************************************************************************/
/* Program Entry Point                                                       */
/*****************************************************************************/
int main()
{{
    OPEN_LOG("test_{module_name}_{pr_number}.ctr", false, 100);
    START_SCRIPT("{module_name}", true);

    run_tests();

    return !END_SCRIPT(true);
}}
/*****************************************************************************/
/* Test Control                                                              */
/*****************************************************************************/
/* run_tests() contains calls to the individual test cases, you can turn test*/
/* cases off by adding comments*/
void run_tests()
{{
{test_calls}

    rule_set("*", "*");
    EXPORT_COVERAGE("test_{module_name}_{pr_number}.cov", cppca_export_replace);
}}
"""

    return cantata_script


def generate_test_implementation(test_func, test_number, function_signatures=None):
    """
    Generate actual test implementation code based on test case information
    Uses LLM intelligence to analyze test cases and generate appropriate Cantata test code
    
    Args:
        test_func: Dictionary containing test case information
        test_number: Test case number for reference
        function_signatures: Optional list of function signatures from C code analysis
        
    Returns:
        String containing C test implementation code
    """
    
    scenario = test_func.get('scenario', '')
    function_name = test_func.get('function_name', '')
    input_values = test_func.get('input', '')
    expected_result = test_func.get('expected', '')
    test_steps = test_func.get('steps', '')
    
    # Get function signature if available
    function_signature = None
    if function_signatures and function_name in function_signatures:
        function_signature = function_signatures[function_name]
    
    # Helper function to extract values from input strings like "n=5" or "a=2,b=3"
    def extract_input_values(input_str):
        values = {}
        if '=' in input_str:
            for part in input_str.split(','):
                if '=' in part:
                    key, val = part.split('=', 1)
                    values[key.strip()] = val.strip()
        return values
    
    # Extract expected value from result string like "CHECK: Return value equals 5" or "CHECK: return value == 5"
    def extract_expected_value(result_str):
        # Try different patterns for expected value extraction
        patterns = [
            r'equals\s+([-\d.]+)',  # "equals 5"
            r'==\s*([-\d.]+)',      # "== 5" or "==5"
            r'return value\s+([-\d.]+)', # "return value 5"
            r'([-\d.]+)(?:\s*\||$)'   # number at end or before pipe
        ]
        
        for pattern in patterns:
            match = re.search(pattern, result_str)
            if match:
                return match.group(1)
        return "0"
    
    # Intelligent function signature analyzer
    def analyze_function_signature(sig, func_name, input_values):
        """Analyze function signature and determine best test implementation approach"""
        
        analysis = {
            'type': 'generic',
            'return_type': 'int',
            'param_types': [],
            'param_names': [],
            'param_values': []
        }
        
        if not sig:
            # No signature provided, infer from input values
            if input_values:
                params = extract_input_values(input_values)
                analysis['param_names'] = list(params.keys())
                analysis['param_values'] = list(params.values())
                analysis['param_types'] = ['int'] * len(params)
            else:
                analysis['param_names'] = ['input']
                analysis['param_values'] = ['5']
                analysis['param_types'] = ['int']
            return analysis
        
        # Parse function signature
        sig_pattern = r'(?:int|float|double|char|void|FILE\*|struct\s+\w+)\s+(\w+)\s*\(([^)]*)\)'
        match = re.search(sig_pattern, sig)
        
        if match:
            analysis['return_type'] = match.group(1).strip()
            params_str = match.group(2).strip()
            
            if params_str and params_str != 'void':
                # Parse individual parameters
                param_list = [p.strip() for p in params_str.split(',')]
                for param in param_list:
                    parts = param.rsplit(None, 1)  # Split type from name
                    if len(parts) == 2:
                        param_type, param_name = parts
                        analysis['param_types'].append(param_type)
                        analysis['param_names'].append(param_name)
                    else:
                        analysis['param_types'].append('int')  # default
                        analysis['param_names'].append(param)
        
        # Get parameter values from test case input
        if input_values:
            params = extract_input_values(input_values)
            analysis['param_values'] = [params.get(name, '0') for name in analysis['param_names']] if analysis['param_names'] else list(params.values())
        else:
            analysis['param_values'] = ['0'] * len(analysis['param_names'])
        
        # Determine function type based on signature patterns
        if any('char' in t or 'char*' in t or 'string' in t.lower() for t in analysis['param_types']):
            analysis['type'] = 'string'
        elif any('FILE' in t for t in analysis['param_types']):
            analysis['type'] = 'file'
        elif any('struct' in t for t in analysis['param_types']):
            analysis['type'] = 'struct'
        elif any('*' in t for t in analysis['param_types']):
            analysis['type'] = 'pointer'
        elif len(analysis['param_names']) > 1:
            analysis['type'] = 'multi_param'
        elif 'float' in analysis['return_type'] or 'double' in analysis['return_type']:
            analysis['type'] = 'floating'
        else:
            analysis['type'] = 'single_int'
        
        return analysis
    
    # Function signature analyzer
    sig_analysis = analyze_function_signature(function_signature, function_name, input_values)
    input_params = extract_input_values(input_values)
    expected_val = extract_expected_value(expected_result)
    
    # Generate test implementation based on intelligent signature analysis
    func_type = sig_analysis['type']
    return_type = sig_analysis['return_type']
    param_types = sig_analysis['param_types']
    param_names = sig_analysis['param_names']
    param_values = sig_analysis['param_values']
    
    # Generate test implementation based on function type analysis
    if func_type == 'string':
        # String manipulation functions
        if len(param_names) >= 2 and 'str1' in param_names[0].lower() and 'str2' in param_names[1].lower():
            implementation = f"""    /* Test scenario: {scenario} */
    char str1[] = {param_values[0] if param_values[0] != '0' else '"hello"'};
    char str2[] = {param_values[1] if param_values[1] != '0' else '"world"'};
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}(str1, str2);
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}"""
        else:
            # Single string parameter
            str_val = param_values[0] if param_values[0] != '0' else '"test string"'
            implementation = f"""    /* Test scenario: {scenario} */
    char input[] = {str_val};
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}(input);
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}"""
    
    elif func_type == 'file':
        # File I/O functions
        implementation = f"""    /* Test scenario: {scenario} */
    FILE* file;
    int expected = {expected_val};
    int result;
    const char* filename = "test_temp.txt";
    
    /* Clean up any existing test file */
    remove(filename);
    
    /* Test file operations */
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}(filename);
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}
    
    /* Clean up test file */
    remove(filename);
    """
    
    elif func_type == 'struct':
        # Structure-based functions
        struct_setup = ""
        if param_values:
            struct_setup = f"    // Initialize struct parameters with values: {', '.join(param_values)}\n"
        
        implementation = f"""    /* Test scenario: {scenario} */
{struct_setup}
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}({', '.join(f'&{name}' for name in param_names)});
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}"""
    
    elif func_type == 'pointer':
        # Pointer-based functions
        param_declarations = []
        for i, (p_type, p_name, p_value) in enumerate(zip(param_types, param_names, param_values)):
            if '*' in p_type:
                param_declarations.append(f"    {p_type} {p_name} = ({p_type}){p_value}")
            else:
                param_declarations.append(f"    {p_type} {p_name} = {p_value}")
        
        implementation = f"""    /* Test scenario: {scenario} */
{chr(10).join(param_declarations)}
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}({', '.join(param_names)});
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}"""
    
    elif func_type == 'multi_param':
        # Multi-parameter functions
        param_declarations = []
        for p_type, p_name, p_value in zip(param_types, param_names, param_values):
            param_declarations.append(f"    {p_type} {p_name} = {p_value}")
        
        implementation = f"""    /* Test scenario: {scenario} */
{chr(10).join(param_declarations)}
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}({', '.join(param_names)});
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %d\\n", result);
    }}"""
    
    elif func_type == 'floating':
        # Floating-point functions
        param_declarations = []
        for p_type, p_name, p_value in zip(param_types, param_names, param_values):
            if 'float' in return_type or 'double' in return_type:
                param_declarations.append(f"    double {p_name} = {p_value}.0")
            else:
                param_declarations.append(f"    int {p_name} = {p_value}")
        
        implementation = f"""    /* Test scenario: {scenario} */
{chr(10).join(param_declarations)}
    double expected = {expected_val};
    double result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}({', '.join(param_names)});
    
    /* Verify result */
    if (fabs(result - expected) > 0.001) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %.6f, expected %.6f\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned %.6f\\n", result);
    }}"""
    
    elif func_type == 'single_int':
        # Single integer parameter functions
        param_name = param_names[0] if param_names else 'input'
        param_value = param_values[0] if param_values else '5'
        param_type = param_types[0] if param_types else 'int'
        
        implementation = f"""    /* Test scenario: {scenario} */
    {param_type} {param_name} = {param_value};
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}(%d)\\n", {param_name});
    result = {function_name}({param_name});
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name}(%d) returned %d, expected %d\\n", {param_name}, result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name}(%d) returned %d\\n", {param_name}, result);
    }}"""
    
    else:
        # Generic fallback for unknown function types
        param_declarations = []
        for p_type, p_name, p_value in zip(param_types, param_names, param_values):
            param_declarations.append(f"    {p_type} {p_name} = {p_value}")
        
        implementation = f"""    /* Test scenario: {scenario} */
{chr(10).join(param_declarations)}
    int expected = {expected_val};
    int result;
    
    TEST_SCRIPT_INFO("Testing {function_name}\\n");
    result = {function_name}({', '.join(param_names)});
    
    /* Verify result */
    if (result != expected) {{
        TEST_SCRIPT_ERROR("FAILED: {function_name} returned %d, expected %d\\n", result, expected);
    }} else {{
        TEST_SCRIPT_INFO("PASSED: {function_name} returned expected result %d\\n", result);
    }}"""
    
    return implementation


def generate_header_file(module_name, pr_number, functions):
    """
    Generate header file for the module being tested
    
    Args:
        module_name: Name of the module
        pr_number: PR number
        functions: List of function names to expose
        
    Returns:
        Header file content
    """
    
    header_content = f"""/*****************************************************************************
 *                          Module Header File                                */
/*****************************************************************************
 *    Filename: module_{pr_number}.h
 *    Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 *****************************************************************************/

#ifndef MODULE_{str(pr_number).upper()}_H_
#define MODULE_{str(pr_number).upper()}_H_

/* Include necessary headers */
#include <stdint.h>
#include <stddef.h>

/* Function declarations */
"""
    
    for func in functions:
        header_content += f"extern int {func}(int param);\n"
    
    header_content += f"""
#endif /* MODULE_{str(pr_number).upper()}_H_ */
"""
    
    return header_content


# =====================================================
# MAIN GENERATOR FUNCTION
# =====================================================

def generate_cantata_tests(diff_text, pr_number, test_cases=None):
    """
    Generate Cantata-compatible tests from C code diff
    
    Args:
        diff_text: C code diff content
        pr_number: PR number
        test_cases: Optional list of parsed test cases
        
    Returns:
        Dictionary containing test files
    """
    
    print("\n" + "=" * 60)
    print("Generating Cantata-Compatible Tests")
    print("=" * 60)
    
    # Extract module name from diff
    module_name = f"module_{pr_number}"
    
    # Extract function signatures from diff for better test generation
    function_signatures = extract_function_signatures_from_diff(diff_text)
    print(f"Extracted {len(function_signatures)} function signatures from diff")
    
    # Generate extern function declarations from signatures
    extern_functions = ["function_under_test"]
    if function_signatures:
        extern_functions = list(function_signatures.keys())
    
    # Generate Cantata test script
    print(f"\nGenerating Cantata test script for module: {module_name}")
    
    # Pass function signatures for intelligent test generation
    cantata_script = convert_to_cantata_format(test_cases, pr_number, module_name, function_signatures)
    
    # Generate header file
    print(f"Generating module header file: {module_name}.h")
    
    # Extract function names for header
    if function_signatures:
        functions = list(function_signatures.keys())
    else:
        functions = ["function_under_test"]
    
    header_content = generate_header_file(module_name, pr_number, functions)
    
    return {
        'test_script': cantata_script,
        'header_file': header_content,
        'module_name': module_name
    }


# =====================================================
# EXAMPLE USAGE
# =====================================================

if __name__ == "__main__":
    print("Cantata Integration Module")
    print("=" * 60)
    print("\nThis module provides functions to integrate AI-generated tests")
    print("with the Cantata testing framework.")
    print("\nKey Functions:")
    print("  - generate_cantata_tests() : Generate Cantata test scripts")
    print("  - convert_to_cantata_format() : Convert test cases to Cantata format")
    print("  - generate_header_file() : Generate module header files")
    print("  - extract_function_signatures_from_diff() : Extract function signatures from C code")