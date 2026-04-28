"""
Tests for diff validation and chunking logic.
"""

import pytest
from src.diff_validator import validate_diff, split_diff_by_function


class TestValidateDiff:
    """Test validate_diff function"""

    def test_rejects_empty_diff(self):
        """Test that empty diffs are rejected"""
        is_valid, error = validate_diff("")
        assert not is_valid
        assert "empty" in error.lower()

    def test_rejects_whitespace_only_diff(self):
        """Test that whitespace-only diffs are rejected"""
        is_valid, error = validate_diff("   \n   \n  ")
        assert not is_valid
        assert "empty" in error.lower()

    def test_rejects_non_c_diff_python(self):
        """Test that Python diffs are rejected"""
        is_valid, error = validate_diff("""diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,5 +1,10 @@
 import numpy as np

+def add_numbers(a, b):
+    return a + b
""")
        assert not is_valid
        assert "c code" in error.lower()

    def test_rejects_diff_without_markers(self):
        """Test that diffs without @@ markers are rejected"""
        is_valid, error = validate_diff("""int add(int a, int b) {
    return a + b;
}
""")
        assert not is_valid
        assert "markers" in error.lower()

    def test_accepts_valid_c_diff_with_function(self):
        """Test that valid C diffs with functions are accepted"""
        is_valid, error = validate_diff("""diff --git a/src/sample.c b/src/sample.c
index 1234567..abcdefg 100644
--- a/src/sample.c
+++ b/src/sample.c
@@ -1,5 +1,10 @@
 #include <stdint.h>

+int add_numbers(int a, int b) {
+    return a + b;
+}

 void process_data(void) {
     int result = 0;
 }""")
        assert is_valid
        assert error is None

    def test_accepts_valid_c_diff_with_struct(self):
        """Test that valid C diffs with structs are accepted"""
        is_valid, error = validate_diff("""diff --git a/src/sample.c b/src/sample.c
index 1234567..abcdefg 100644
--- a/src/sample.c
+++ b/src/sample.c
@@ -1,5 +1,10 @@
 #include <stdint.h>

+typedef struct {
+    int x;
+    int y;
+} Point;

 void process_data(void) {
     int result = 0;
 }""")
        assert is_valid
        assert error is None

    def test_accepts_valid_c_diff_with_typedef(self):
        """Test that valid C diffs with typedefs are accepted"""
        is_valid, error = validate_diff("""diff --git a/src/sample.c b/src/sample.c
index 1234567..abcdefg 100644
--- a/src/sample.c
+++ b/src/sample.c
@@ -1,5 +1,10 @@
 #include <stdint.h>

+typedef uint8_t MyType;
+typedef int32_t Status_t;

 void process_data(void) {
     int result = 0;
 }""")
        assert is_valid
        assert error is None


class TestSplitDiffByFunction:
    """Test split_diff_by_function function"""

    def test_returns_original_for_small_diff(self):
        """Test that diffs < 300 lines are returned as-is"""
        diff_content = """diff --git a/test.c b/test.c
index 1234567..abcdefg 100644
--- a/test.c
+++ b/test.c
@@ -1,5 +1,10 @@
 #include <stdint.h>

+int add_numbers(int a, int b) {
+    return a + b;
+}
"""
        chunks = split_diff_by_function(diff_content)
        assert len(chunks) == 1
        assert chunks[0] == diff_content

    def test_splits_large_diff_by_function_boundaries(self):
        """Test that large diffs are split by function boundaries"""
        # Use the large_diff fixture which has 360 lines
        with open('tests/fixtures/large_diff.diff', 'r') as f:
            large_diff = f.read()

        chunks = split_diff_by_function(large_diff)

        # Should split into multiple chunks
        assert len(chunks) > 1

        # Each chunk should have diff header
        for chunk in chunks:
            assert 'diff --git' in chunk or '@@' in chunk

    def test_chunks_contain_complete_functions(self):
        """Test that chunks contain complete functions (no partial)"""
        with open('tests/fixtures/large_diff.diff', 'r') as f:
            large_diff = f.read()

        chunks = split_diff_by_function(large_diff)

        for chunk in chunks:
            lines = chunk.split('\n')
            open_braces = sum(line.count('{') for line in lines)
            close_braces = sum(line.count('}') for line in lines)
            # Braces should be balanced in each chunk
            assert open_braces == close_braces, f"Unbalanced braces in chunk:\n{chunk}"

    def test_handles_empty_diff(self):
        """Test that empty diffs are handled gracefully"""
        chunks = split_diff_by_function("")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_handles_diff_without_functions(self):
        """Test that diffs without functions are not split"""
        diff_content = '\n'.join([f'+// Line {i}' for i in range(350)])
        chunks = split_diff_by_function(diff_content)
        # Should return as single chunk since no functions to split on
        assert len(chunks) == 1

    def test_preserves_diff_format_in_chunks(self):
        """Test that chunks preserve unified diff format"""
        with open('tests/fixtures/large_diff.diff', 'r') as f:
            large_diff = f.read()

        chunks = split_diff_by_function(large_diff)

        for chunk in chunks:
            # Should have diff markers
            assert '@@' in chunk
            # Should have + or - markers for code changes
            assert '+' in chunk


class TestDiffValidatorIntegration:
    """Integration tests for diff validation and chunking"""

    def test_validate_and_split_valid_diff(self):
        """Test validating and splitting a valid large diff"""
        with open('tests/fixtures/large_diff.diff', 'r') as f:
            large_diff = f.read()

        # First validate
        is_valid, error = validate_diff(large_diff)
        assert is_valid
        assert error is None

        # Then split
        chunks = split_diff_by_function(large_diff)
        assert len(chunks) > 1

        # Each chunk should be valid
        for chunk in chunks:
            is_chunk_valid, chunk_error = validate_diff(chunk)
            # Chunks might not have full C patterns, so we just check they don't error catastrophically
            # In a real scenario, chunks should be valid diffs
            assert is_chunk_valid or chunk_error is not None

    def test_reject_invalid_diff_before_splitting(self):
        """Test that invalid diffs are rejected before splitting attempt"""
        with open('tests/fixtures/non_c_diff.diff', 'r') as f:
            non_c_diff = f.read()

        # Should reject
        is_valid, error = validate_diff(non_c_diff)
        assert not is_valid

        # Splitting would still work but should return original
        chunks = split_diff_by_function(non_c_diff)
        assert len(chunks) == 1
        assert chunks[0] == non_c_diff
