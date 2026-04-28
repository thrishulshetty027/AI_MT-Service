# Test Cases - PR #167
Generated at: 2026-04-23 16:44:19
---

| Test Case ID | Function Name | Test Scenario | Input Values | Pre-Conditions | Test Steps | Expected Result | Post-Conditions | Test Type |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC_001 | sumPositive | Sum of multiple positive numbers | arr={1,2,3,4}, size=4 | none | TEST_SCRIPT_INFO: Summing positive integers ; Function call: sumPositive(arr, 4) ; Coverage: normal | 10 | none | normal |
| TC_002 | sumPositive | Mixed positive and negative numbers | arr={10,-5,20,-10}, size=4 | none | TEST_SCRIPT_INFO: Summing only positive values in mixed array ; Function call: sumPositive(arr, 4) ; Coverage: normal | 30 | none | normal |
| TC_003 | sumPositive | Array with no positive numbers | arr={-1,-2,0}, size=3 | none | TEST_SCRIPT_INFO: Testing array with no positives ; Function call: sumPositive(arr, 3) ; Coverage: edge | 0 | none | edge |
| TC_004 | sumPositive | Empty array | arr={}, size=0 | none | TEST_SCRIPT_INFO: Testing size zero ; Function call: sumPositive(arr, 0) ; Coverage: boundary | 0 | none | boundary |
| TC_005 | countNegative | Count multiple negative numbers | arr={-1,-2,-3,5}, size=4 | none | TEST_SCRIPT_INFO: Counting negative integers ; Function call: countNegative(arr, 4) ; Coverage: normal | 3 | none | normal |
| TC_006 | countNegative | Array with no negative numbers | arr={1,2,0}, size=3 | none | TEST_SCRIPT_INFO: Testing array with no negatives ; Function call: countNegative(arr, 3) ; Coverage: edge | 0 | none | edge |
| TC_007 | countNegative | Empty array | arr={}, size=0 | none | TEST_SCRIPT_INFO: Testing size zero ; Function call: countNegative(arr, 0) ; Coverage: boundary | 0 | none | boundary |
| TC_008 | firstZeroIndex | Zero exists in the middle of the array | arr={1,2,0,4}, size=4 | none | TEST_SCRIPT_INFO: Finding zero at index 2 ; Function call: firstZeroIndex(arr, 4) ; Coverage: normal | 2 | none | normal |
| TC_009 | firstZeroIndex | Zero is the first element | arr={0,1,2}, size=3 | none | TEST_SCRIPT_INFO: Finding zero at start ; Function call: firstZeroIndex(arr, 3) ; Coverage: boundary | 0 | none | boundary |
| TC_010 | firstZeroIndex | Zero is the last element | arr={1,2,0}, size=3 | none | TEST_SCRIPT_INFO: Finding zero at end ; Function call: firstZeroIndex(arr, 3) ; Coverage: boundary | 2 | none | boundary |
| TC_011 | firstZeroIndex | No zero present in array | arr={1,2,3}, size=3 | none | TEST_SCRIPT_INFO: Searching for non-existent zero ; Function call: firstZeroIndex(arr, 3) ; Coverage: edge | -1 | none | edge |
| TC_012 | firstZeroIndex | Empty array | arr={}, size=0 | none | TEST_SCRIPT_INFO: Searching empty array ; Function call: firstZeroIndex(arr, 0) ; Coverage: boundary | -1 | none | boundary |