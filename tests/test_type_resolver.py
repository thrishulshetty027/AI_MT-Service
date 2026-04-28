"""
Tests for type classification and typedef resolution.
"""

import pytest
from src.type_resolver import (
    CType,
    C_TYPE_TO_CTYPE,
    resolve_typedef_chain,
    classify_parameter,
    get_zero_value,
    get_null_value,
    is_scalar,
    is_pointer_like
)


class TestCTypeEnum:
    """Test CType enum"""

    def test_enum_has_all_values(self):
        """Test that CType has all required values"""
        values = [t.value for t in CType]

        # Unsigned integers
        assert 'UINT8' in values
        assert 'UINT16' in values
        assert 'UINT32' in values
        assert 'UINT64' in values

        # Signed integers
        assert 'INT8' in values
        assert 'INT16' in values
        assert 'INT32' in values
        assert 'INT64' in values

        # Floating point
        assert 'FLOAT' in values
        assert 'DOUBLE' in values

        # Complex types
        assert 'STRUCT' in values
        assert 'POINTER' in values
        assert 'ARRAY' in values

        # Boolean and void
        assert 'BOOL' in values
        assert 'VOID' in values
        assert 'UNKNOWN' in values

    def test_enum_has_15_or_more_values(self):
        """Test that there are at least 15 values"""
        values = list(CType)
        assert len(values) >= 15


class TestCTypeMapping:
    """Test C_TYPE_TO_CTYPE mapping"""

    def test_maps_standard_c_unsigned_types(self):
        """Test mapping of standard C unsigned types"""
        assert C_TYPE_TO_CTYPE['uint8_t'] == CType.UINT8
        assert C_TYPE_TO_CTYPE['uint16_t'] == CType.UINT16
        assert C_TYPE_TO_CTYPE['uint32_t'] == CType.UINT32
        assert C_TYPE_TO_CTYPE['uint64_t'] == CType.UINT64
        assert C_TYPE_TO_CTYPE['unsigned char'] == CType.UINT8
        assert C_TYPE_TO_CTYPE['unsigned short'] == CType.UINT16
        assert C_TYPE_TO_CTYPE['unsigned int'] == CType.UINT32
        assert C_TYPE_TO_CTYPE['unsigned long'] == CType.UINT64

    def test_maps_standard_c_signed_types(self):
        """Test mapping of standard C signed types"""
        assert C_TYPE_TO_CTYPE['int8_t'] == CType.INT8
        assert C_TYPE_TO_CTYPE['int16_t'] == CType.INT16
        assert C_TYPE_TO_CTYPE['int32_t'] == CType.INT32
        assert C_TYPE_TO_CTYPE['int64_t'] == CType.INT64
        assert C_TYPE_TO_CTYPE['char'] == CType.INT8
        assert C_TYPE_TO_CTYPE['short'] == CType.INT16
        assert C_TYPE_TO_CTYPE['int'] == CType.INT32
        assert C_TYPE_TO_CTYPE['long'] == CType.INT64

    def test_maps_floating_point_types(self):
        """Test mapping of floating point types"""
        assert C_TYPE_TO_CTYPE['float'] == CType.FLOAT
        assert C_TYPE_TO_CTYPE['double'] == CType.DOUBLE
        assert C_TYPE_TO_CTYPE['float32_t'] == CType.FLOAT
        assert C_TYPE_TO_CTYPE['float64_t'] == CType.DOUBLE

    def test_maps_bool_types(self):
        """Test mapping of bool types"""
        assert C_TYPE_TO_CTYPE['bool'] == CType.BOOL
        assert C_TYPE_TO_CTYPE['_Bool'] == CType.BOOL
        assert C_TYPE_TO_CTYPE['boolean'] == CType.BOOL

    def test_maps_void_type(self):
        """Test mapping of void type"""
        assert C_TYPE_TO_CTYPE['void'] == CType.VOID


class TestResolveTypedefChain:
    """Test typedef chain resolution"""

    def test_resolves_single_level_typedef(self):
        """Test resolution of single-level typedef"""
        typedef_map = {
            'MyType': 'uint8_t',
            'Status_t': 'int32_t'
        }

        assert resolve_typedef_chain('MyType', typedef_map) == 'uint8_t'
        assert resolve_typedef_chain('Status_t', typedef_map) == 'int32_t'

    def test_resolves_multi_level_typedef(self):
        """Test resolution of multi-level typedef chain"""
        typedef_map = {
            'MyType': 'uint8',
            'uint8': 'uint8_t'
        }

        assert resolve_typedef_chain('MyType', typedef_map) == 'uint8_t'

    def test_returns_original_if_not_in_map(self):
        """Test that original type is returned if not in typedef map"""
        typedef_map = {
            'MyType': 'uint8_t'
        }

        assert resolve_typedef_chain('int', typedef_map) == 'int'
        assert resolve_typedef_chain('CustomType', typedef_map) == 'CustomType'

    def test_handles_cycles(self):
        """Test that typedef cycles are detected and handled"""
        typedef_map = {
            'TypeA': 'TypeB',
            'TypeB': 'TypeC',
            'TypeC': 'TypeA'  # Cycle!
        }

        # Should stop recursion and return one of the types
        result = resolve_typedef_chain('TypeA', typedef_map)
        assert result in ['TypeA', 'TypeB', 'TypeC']


class TestClassifyParameter:
    """Test parameter classification"""

    def test_classifies_scalar_uint_types(self):
        """Test classification of unsigned integer types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('uint8_t', typedef_map)
        assert c_type == CType.UINT8
        assert resolved == 'uint8_t'

        c_type, resolved = classify_parameter('uint16_t', typedef_map)
        assert c_type == CType.UINT16

        c_type, resolved = classify_parameter('uint32_t', typedef_map)
        assert c_type == CType.UINT32

    def test_classifies_scalar_int_types(self):
        """Test classification of signed integer types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('int8_t', typedef_map)
        assert c_type == CType.INT8

        c_type, resolved = classify_parameter('int16_t', typedef_map)
        assert c_type == CType.INT16

        c_type, resolved = classify_parameter('int32_t', typedef_map)
        assert c_type == CType.INT32

    def test_classifies_float_types(self):
        """Test classification of float types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('float', typedef_map)
        assert c_type == CType.FLOAT
        assert resolved == 'float'

        c_type, resolved = classify_parameter('double', typedef_map)
        assert c_type == CType.DOUBLE

    def test_classifies_bool_type(self):
        """Test classification of bool type"""
        typedef_map = {}

        c_type, resolved = classify_parameter('bool', typedef_map)
        assert c_type == CType.BOOL

    def test_classifies_pointer_types(self):
        """Test classification of pointer types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('uint8_t*', typedef_map)
        assert c_type == CType.POINTER
        assert resolved == 'uint8_t'

        c_type, resolved = classify_parameter('void*', typedef_map)
        assert c_type == CType.POINTER
        assert resolved == 'void'

    def test_classifies_array_types(self):
        """Test classification of array types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('uint8_t[]', typedef_map)
        assert c_type == CType.ARRAY
        assert resolved == 'uint8_t'

        c_type, resolved = classify_parameter('int arr[]', typedef_map)
        assert c_type == CType.ARRAY
        assert resolved == 'int'

    def test_classifies_struct_types(self):
        """Test classification of struct types"""
        typedef_map = {}
        struct_definitions = {
            'MyStruct': ['field1', 'field2']
        }

        c_type, resolved = classify_parameter('struct MyStruct', typedef_map)
        assert c_type == CType.STRUCT
        assert resolved == 'MyStruct'

        c_type, resolved = classify_parameter('MyStruct_t', typedef_map)
        assert c_type == CType.UNKNOWN  # Not a struct without typedef

    def test_classifies_with_typedef_resolution(self):
        """Test classification with typedef resolution"""
        typedef_map = {
            'MyType_t': 'uint8_t',
            'Status_t': 'int32_t'
        }

        c_type, resolved = classify_parameter('MyType_t', typedef_map)
        assert c_type == CType.UINT8
        assert resolved == 'uint8_t'

        c_type, resolved = classify_parameter('Status_t*', typedef_map)
        assert c_type == CType.POINTER
        assert resolved == 'int32_t'

    def test_classifies_unknown_types(self):
        """Test classification of unknown/custom types"""
        typedef_map = {}

        c_type, resolved = classify_parameter('CustomUnknownType', typedef_map)
        assert c_type == CType.UNKNOWN
        assert resolved == 'CustomUnknownType'


class TestGetZeroValue:
    """Test zero value determination"""

    def test_returns_zero_u_for_unsigned_ints(self):
        """Test that unsigned ints return '0u'"""
        assert get_zero_value(CType.UINT8) == '0u'
        assert get_zero_value(CType.UINT16) == '0u'
        assert get_zero_value(CType.UINT32) == '0u'
        assert get_zero_value(CType.UINT64) == '0u'

    def test_returns_zero_for_signed_ints(self):
        """Test that signed ints return '0'"""
        assert get_zero_value(CType.INT8) == '0'
        assert get_zero_value(CType.INT16) == '0'
        assert get_zero_value(CType.INT32) == '0'
        assert get_zero_value(CType.INT64) == '0'

    def test_returns_zero_f_for_float(self):
        """Test that float returns '0.0f'"""
        assert get_zero_value(CType.FLOAT) == '0.0f'

    def test_returns_zero_for_double(self):
        """Test that double returns '0.0'"""
        assert get_zero_value(CType.DOUBLE) == '0.0'

    def test_returns_false_for_bool(self):
        """Test that bool returns 'FALSE'"""
        assert get_zero_value(CType.BOOL) == 'FALSE'

    def test_returns_null_ptr_for_pointer_types(self):
        """Test that pointer-like types return 'NULL_PTR'"""
        assert get_zero_value(CType.POINTER) == 'NULL_PTR'
        assert get_zero_value(CType.ARRAY) == 'NULL_PTR'
        assert get_zero_value(CType.STRUCT) == 'NULL_PTR'

    def test_returns_empty_for_void(self):
        """Test that void returns empty string"""
        assert get_zero_value(CType.VOID) == ''

    def test_returns_zero_for_unknown(self):
        """Test that unknown returns '0'"""
        assert get_zero_value(CType.UNKNOWN) == '0'


class TestGetNullValue:
    """Test null value determination"""

    def test_returns_null_ptr_for_pointer_types(self):
        """Test that pointer-like types return 'NULL_PTR'"""
        assert get_null_value(CType.POINTER) == 'NULL_PTR'
        assert get_null_value(CType.ARRAY) == 'NULL_PTR'
        assert get_null_value(CType.STRUCT) == 'NULL_PTR'

    def test_returns_none_for_scalar_types(self):
        """Test that scalar types return None"""
        assert get_null_value(CType.UINT8) is None
        assert get_null_value(CType.INT32) is None
        assert get_null_value(CType.FLOAT) is None
        assert get_null_value(CType.BOOL) is None

    def test_returns_none_for_void_and_unknown(self):
        """Test that void and unknown return None"""
        assert get_null_value(CType.VOID) is None
        assert get_null_value(CType.UNKNOWN) is None


class TestIsScalar:
    """Test is_scalar helper"""

    def test_returns_true_for_scalar_types(self):
        """Test that scalar types return True"""
        assert is_scalar(CType.UINT8) is True
        assert is_scalar(CType.INT32) is True
        assert is_scalar(CType.FLOAT) is True
        assert is_scalar(CType.DOUBLE) is True
        assert is_scalar(CType.BOOL) is True

    def test_returns_false_for_non_scalar_types(self):
        """Test that non-scalar types return False"""
        assert is_scalar(CType.STRUCT) is False
        assert is_scalar(CType.POINTER) is False
        assert is_scalar(CType.ARRAY) is False
        assert is_scalar(CType.VOID) is False
        assert is_scalar(CType.UNKNOWN) is False


class TestIsPointerLike:
    """Test is_pointer_like helper"""

    def test_returns_true_for_pointer_like_types(self):
        """Test that pointer-like types return True"""
        assert is_pointer_like(CType.POINTER) is True
        assert is_pointer_like(CType.ARRAY) is True
        assert is_pointer_like(CType.STRUCT) is True

    def test_returns_false_for_non_pointer_types(self):
        """Test that non-pointer types return False"""
        assert is_pointer_like(CType.UINT8) is False
        assert is_pointer_like(CType.INT32) is False
        assert is_pointer_like(CType.FLOAT) is False
        assert is_pointer_like(CType.BOOL) is False
        assert is_pointer_like(CType.VOID) is False
        assert is_pointer_like(CType.UNKNOWN) is False
