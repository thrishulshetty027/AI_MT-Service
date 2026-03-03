#!/usr/bin/env python3
"""
Test the current test case format and identify issues
"""
import re

# Example of what the model might be generating
example_output = """| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |
|--------------|---------------|---------------|--------------|----------------|------------|-----------------|-----------------|-----------|
| TC_001 | add | Normal addition of two positive integers | a = 5, b = 3 | None | Call add(5, 3) | Return 8 | Function returns sum | Normal |
| TC_002 | add | Normal addition of two negative integers | a = -5, b = -3 | None | Call add(-5, -3) | Return -8 | Function returns sum | Normal |
| TC_003 | add | Normal addition of positive and negative numbers | a = 10, b = -4 | None | Call add(10, -4) | Return 6 | Function returns sum | Normal |"""

# Check if it's a proper markdown table
def check_markdown_table(table_text):
    lines = table_text.strip().split('\n')
    
    # Check minimum lines
    if len(lines) < 2:
        return False, "Too few lines"
    
    # Check header line format
    header = lines[0]
    header_parts = [p.strip() for p in header.split('|')]
    
    if len(header_parts) != 10:
        return False, f"Expected 10 columns, got {len(header_parts)}"
    
    # Check column headers
    expected_headers = [
        'Test Case ID',
        'Function Name',
        'Test Scenario',
        'Input Values',
        'Pre-Conditions',
        'Test Steps',
        'Expected Result',
        'Post-Conditions',
        'Test Type'
    ]
    
    for i, expected in enumerate(expected_headers):
        if header_parts[i] != expected:
            return False, f"Column {i+1} mismatch: expected '{expected}', got '{header_parts[i]}'"
    
    # Check that separator line exists
    if len(lines) < 2:
        return False, "Missing separator line"
    
    separator = lines[1]
    separator_parts = [p.strip() for p in separator.split('|')]
    
    if len(separator_parts) != 10:
        return False, f"Separator has wrong number of columns: {len(separator_parts)}"
    
    return True, "Valid markdown table"

# Test the current format
is_valid, message = check_markdown_table(example_output)
print(f"Format validation: {message}")
print(f"Valid: {is_valid}")

# Check if it matches expected format
print("\nExpected format:")
print("| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |")
print("\nActual format:")
print(example_output)

# Identify potential issues
print("\nPotential issues:")
print("1. Column alignment: Check if all columns are properly aligned")
print("2. Column width: Ensure columns are wide enough for content")
print("3. Table headers: Ensure all 9 columns are present")
print("4. Data rows: Ensure each row has all required data")
