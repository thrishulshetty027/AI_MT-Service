"""
Tests for context assembly from diffs.
"""

import pytest
from src.context_assembler import (
    ContextPackage,
    extract_context_from_diff,
    _strip_diff_markers,
    _extract_struct_definitions,
    _extract_typedefs,
    _extract_macros,
    _detect_hal_functions
)


class TestStripDiffMarkers:
    """Test _strip_diff_markers helper function"""

    def test_removes_diff_markers(self):
        """Test that diff markers are removed"""
        diff = """diff --git a/test.c b/test.c
index 1234567..abcdefg 100644
--- a/test.c
+++ b/test.c
@@ -1,5 +1,10 @@
 #include <stdint.h>

+int add(int a, int b) {
+    return a + b;
+}
"""
        result = _strip_diff_markers(diff)
        assert "diff --git" not in result
        assert "--- a/test.c" not in result
        assert "+++ b/test.c" not in result
        assert "@@" not in result

    def test_strips_plus_prefix(self):
        """Test that + prefix is stripped from added lines"""
        diff = """+int add(int a, int b) {
+    return a + b;
+}"""
        result = _strip_diff_markers(diff)
        assert "int add(int a, int b) {" in result
        assert "    return a + b;" in result
        assert "+int add" not in result

    def test_skips_removed_lines(self):
        """Test that lines starting with - are skipped"""
        diff = """-int old_function(void) {
-    return 0;
-}
+int new_function(void) {
+    return 1;
+}"""
        result = _strip_diff_markers(diff)
        assert "old_function" not in result
        assert "new_function" in result

    def test_keeps_context_lines(self):
        """Test that context lines (no +/-) are kept"""
        diff = """#include <stdint.h>

+int add(int a, int b) {
+    return a + b;
+}

 void process_data(void) {
     int result = 0;
 }"""
        result = _strip_diff_markers(diff)
        assert "#include <stdint.h>" in result
        assert "void process_data(void)" in result


class TestExtractFunctionSignatures:
    """Test function signature extraction"""

    def test_extract_simple_function(self):
        """Test extraction of simple function signature"""
        with open('tests/fixtures/sample_c.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert len(context.function_signatures) >= 1

        # Find add_numbers function
        add_func = None
        for func in context.function_signatures:
            if func.get('name') == 'add_numbers':
                add_func = func
                break

        assert add_func is not None
        assert add_func['return_type'] == 'int'
        # Parameters is a list of dicts with 'name' and 'type'
        param_names = [p['name'] for p in add_func['parameters']]
        assert 'a' in param_names
        assert 'b' in param_names

    def test_extract_function_with_pointer_param(self):
        """Test extraction of function with pointer parameter"""
        with open('tests/fixtures/sample_c.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)

        # Find calculate_checksum function
        checksum_func = None
        for func in context.function_signatures:
            if func.get('name') == 'calculate_checksum':
                checksum_func = func
                break

        assert checksum_func is not None
        assert checksum_func['return_type'] == 'uint32_t'
        # Should have pointer parameter
        assert any('data' in str(p) for p in checksum_func['parameters'])

    def test_extract_void_return_function(self):
        """Test extraction of void return function"""
        with open('tests/fixtures/sample_c.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)

        # Find process_data function
        process_func = None
        for func in context.function_signatures:
            if func.get('name') == 'process_data':
                process_func = func
                break

        assert process_func is not None
        assert process_func['return_type'] == 'void'


class TestExtractStructDefinitions:
    """Test struct definition extraction"""

    def test_extract_struct_name_and_fields(self):
        """Test extraction of struct name and field names"""
        with open('tests/fixtures/sample_c_with_struct.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert len(context.struct_definitions) > 0

        # Should have SensorData_t struct
        assert 'SensorData_t' in context.struct_definitions
        fields = context.struct_definitions['SensorData_t']
        assert 'id' in fields
        assert 'value' in fields
        assert 'timestamp' in fields

    def test_handle_nested_structs(self):
        """Test that nested structs are handled (extract outer struct only)"""
        # This test verifies that if there are nested structs,
        # the outer struct name is extracted
        diff = """+typedef struct {
+    int x;
+    struct {
+        int y;
+        int z;
+    } nested;
+} OuterStruct_t;
"""
        context = extract_context_from_diff(diff)
        # Should have OuterStruct_t
        assert 'OuterStruct_t' in context.struct_definitions
        # Fields should include 'nested'
        assert 'nested' in context.struct_definitions['OuterStruct_t']


class TestExtractTypedefs:
    """Test typedef extraction"""

    def test_extract_simple_typedef(self):
        """Test extraction of simple typedef"""
        with open('tests/fixtures/sample_c_with_typedef.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert 'MyType' in context.typedef_map
        assert context.typedef_map['MyType'] == 'uint8_t'

    def test_extract_multiple_typedefs(self):
        """Test extraction of multiple typedefs"""
        with open('tests/fixtures/sample_c_with_typedef.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert 'MyType' in context.typedef_map
        assert 'Status_t' in context.typedef_map
        assert 'Error_t' in context.typedef_map
        assert 'BufferPtr' in context.typedef_map

    def test_extract_pointer_typedef(self):
        """Test extraction of pointer typedef"""
        with open('tests/fixtures/sample_c_with_typedef.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert 'BufferPtr' in context.typedef_map
        assert 'uint8_t' in context.typedef_map['BufferPtr']

    def test_extract_struct_typedef(self):
        """Test extraction of struct typedef"""
        diff = """+typedef struct {
+    int x;
+    int y;
+} Point_t;
"""
        context = extract_context_from_diff(diff)
        assert 'Point_t' in context.typedef_map


class TestExtractMacros:
    """Test macro extraction"""

    def test_extract_simple_define(self):
        """Test extraction of simple #define"""
        diff = """+#define MAX_CHANNELS 32
+#define FALSE 0
+#define TRUE 1
"""
        context = extract_context_from_diff(diff)
        assert context.macro_constants['MAX_CHANNELS'] == '32'
        assert context.macro_constants['FALSE'] == '0'
        assert context.macro_constants['TRUE'] == '1'

    def test_extract_define_with_expression(self):
        """Test extraction of #define with expression"""
        diff = """+#define MAX(a, b) ((a) > (b) ? (a) : (b))
+#define BUFFER_SIZE (10 + 5)
"""
        context = extract_context_from_diff(diff)
        assert 'MAX' in context.macro_constants
        assert 'BUFFER_SIZE' in context.macro_constants

    def test_skip_conditional_compilation(self):
        """Test that #ifdef, #ifndef, #endif are skipped"""
        diff = """+#ifdef DEBUG
+#define LOG_ENABLED 1
+#endif
+#ifndef RELEASE
+#define TEST_MODE 1
+#endif
"""
        context = extract_context_from_diff(diff)
        # Should not include conditional directives
        assert '#ifdef' not in str(context.macro_constants)
        assert '#ifndef' not in str(context.macro_constants)


class TestDetectHalFunctions:
    """Test HAL function detection"""

    def test_detect_hal_functions(self):
        """Test detection of HAL_ prefixed functions"""
        diff = """+void process_data(void) {
+    uint8_t value = HAL_ADC_Read(ADC_CHANNEL_1);
+    Rte_Write_Port_Output(value);
+    Com_SendSignal(SIGNAL_ID, value);
+}
"""
        context = extract_context_from_diff(diff)
        assert 'HAL_ADC_Read' in context.hal_functions
        assert 'Rte_Write_Port_Output' in context.hal_functions
        assert 'Com_SendSignal' in context.hal_functions

    def test_ignore_regular_functions(self):
        """Test that regular functions are not detected as HAL"""
        diff = """+void process_data(void) {
+    int value = calculate_value(10);
+    update_buffer(buffer, size);
+}
"""
        context = extract_context_from_diff(diff)
        # Should not detect these as HAL functions
        assert 'calculate_value' not in context.hal_functions
        assert 'update_buffer' not in context.hal_functions

    def test_detect_hal_with_different_prefixes(self):
        """Test detection with different HAL prefixes"""
        diff = """+void process(void) {
+    HAL_Init();
+    HAL_DeInit();
+    Rte_Call_Port();
+    Com_ReceiveSignal();
+}
"""
        context = extract_context_from_diff(diff)
        assert 'HAL_Init' in context.hal_functions
        assert 'HAL_DeInit' in context.hal_functions
        assert 'Rte_Call_Port' in context.hal_functions
        assert 'Com_ReceiveSignal' in context.hal_functions


class TestExtractContextFromDiff:
    """Test complete context extraction"""

    def test_returns_complete_context_package(self):
        """Test that complete ContextPackage is returned"""
        with open('tests/fixtures/sample_c.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert isinstance(context, ContextPackage)
        assert context.diff_text == diff
        assert len(context.function_signatures) >= 1

    def test_works_with_struct_diff(self):
        """Test extraction with struct fixture"""
        with open('tests/fixtures/sample_c_with_struct.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert len(context.struct_definitions) > 0
        assert len(context.function_signatures) >= 2

    def test_works_with_typedef_diff(self):
        """Test extraction with typedef fixture"""
        with open('tests/fixtures/sample_c_with_typedef.diff', 'r') as f:
            diff = f.read()

        context = extract_context_from_diff(diff)
        assert len(context.typedef_map) >= 3
        assert len(context.function_signatures) >= 4
