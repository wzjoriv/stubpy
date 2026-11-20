"""
Named constants of compiled-module support: C API format units, member types and skipped members.
"""
from __future__ import annotations

EXTENSION_FILE_SUFFIXES: frozenset[str] = frozenset({".pyd", ".so"})

COMPILED_SOURCE_SUFFIXES: tuple[str, ...] = (".pyx", ".pxd", ".c", ".cpp", ".cc", ".cxx")

COMPILED_SKIP_MEMBERS: frozenset[str] = frozenset({
    "__doc__", "__module__", "__dict__", "__weakref__", "__qualname__", "__slots__",
    "__reduce__", "__reduce_ex__", "__setstate__", "__getstate__", "__reduce_cython__", "__setstate_cython__",
    "__pyx_vtable__", "_pybind11_conduit_v1_", "__members__", "__entries", "__nb_enum__",
    "__annotations__", "__abstractmethods__", "__match_args__",
})

COMPILED_ENUM_INTERNALS: frozenset[str] = frozenset({
    "name", "value", "_generate_next_value_", "_new_member_", "_use_args_", "_member_names_", "_member_map_",
    "_value2member_map_", "_unhashable_values_", "_member_type_", "_value_repr_", "_missing_",
})

COMPILED_RECEIVER_NAMES: frozenset[str] = frozenset({"self", "cls", "arg0", "type", "$self", "$type", "$cls"})

#: NumPy calls that return a new array
NUMPY_ARRAY_FACTORIES: frozenset[str] = frozenset({
    "array", "asarray", "ascontiguousarray", "empty", "empty_like", "full", "full_like", "ones", "ones_like",
    "zeros", "zeros_like", "arange", "copy",
})

#: Builtins whose call result has a fixed type
BUILTIN_CALL_TYPES: dict[str, str] = {
    "int": "int", "float": "float", "complex": "complex", "str": "str", "bytes": "bytes", "bool": "bool",
    "len": "int", "list": "list", "dict": "dict", "tuple": "tuple", "set": "set", "frozenset": "frozenset",
    "repr": "str", "hash": "int", "ord": "int", "chr": "str", "isinstance": "bool", "callable": "bool",
}

#: C API ``PyArg_Parse*`` format units (and ``Py_BuildValue`` ones) to Python types; ``None`` is ``Any``
CAPI_FORMAT_TYPES: dict[str, str | None] = {
    **dict.fromkeys(("b", "B", "h", "H", "i", "I", "l", "k", "L", "K", "n"), "int"),
    "f": "float", "d": "float", "D": "complex", "c": "bytes", "C": "str", "p": "bool",
    "s": "str", "s#": "str", "s*": "str | typing_extensions.Buffer", "U": "str",
    "z": "str | None", "z#": "str | None", "z*": "str | typing_extensions.Buffer | None",
    "y": "bytes", "y#": "bytes", "y*": "typing_extensions.Buffer", "S": "bytes", "Y": "bytearray",
    "w*": "typing_extensions.Buffer", "es": "str", "et": "str | bytes", "es#": "str", "et#": "str | bytes",
    "O": None, "O!": None, "O&": None, "N": None,
}

#: Varargs each ``PyArg_Parse*`` unit consumes
CAPI_FORMAT_ARGS: dict[str, int] = {"s#": 2, "z#": 2, "y#": 2, "O!": 2, "O&": 2, "es": 2, "et": 2, "es#": 3, "et#": 3}

#: Builtin type objects (``O!`` with ``&PyList_Type``) to their Python type
CAPI_TYPE_OBJECTS: dict[str, str] = {
    "PyLong_Type": "int", "PyFloat_Type": "float", "PyComplex_Type": "complex", "PyBool_Type": "bool",
    "PyUnicode_Type": "str", "PyBytes_Type": "bytes", "PyByteArray_Type": "bytearray", "PyList_Type": "list",
    "PyTuple_Type": "tuple", "PyDict_Type": "dict", "PySet_Type": "set", "PyFrozenSet_Type": "frozenset",
    "PySlice_Type": "slice", "PyMemoryView_Type": "memoryview", "PyType_Type": "type",
}

#: ``PyMemberDef`` type codes (``T_INT`` / ``Py_T_INT``) to Python types
CAPI_MEMBER_TYPES: dict[str, str] = {
    **dict.fromkeys(("SHORT", "INT", "LONG", "LONGLONG", "USHORT", "UINT", "ULONG", "ULONGLONG", "BYTE", "UBYTE",
                     "PYSSIZET"), "int"),
    "FLOAT": "float", "DOUBLE": "float", "BOOL": "bool", "CHAR": "str", "STRING": "str", "STRING_INPLACE": "str",
    "OBJECT": "Any", "OBJECT_EX": "Any",
}

#: Calls whose result has a fixed type when a C function returns it
CAPI_RETURN_CALLS: tuple[tuple[str, str], ...] = (
    (r"PyLong_From\w+", "int"), (r"PyFloat_From\w+", "float"), (r"PyBool_From\w+", "bool"),
    (r"PyUnicode_(?:From\w+|Decode\w*)", "str"), (r"PyBytes_From\w+", "bytes"), (r"PyComplex_From\w+", "complex"),
)

#: Return statements that mean ``None`` / ``bool``
CAPI_RETURN_MACROS: dict[str, str] = {"Py_RETURN_NONE": "None", "Py_RETURN_TRUE": "bool", "Py_RETURN_FALSE": "bool"}

#: Argument Clinic converters to Python types; unknown ones are ``Any``
CAPI_CLINIC_TYPES: dict[str, str] = {
    **dict.fromkeys(("int", "long", "long long", "short", "char", "unsigned_int", "unsigned_long",
                     "unsigned_long_long", "unsigned_short", "unsigned_char", "Py_ssize_t", "size_t", "ssize_t",
                     "Py_hash_t", "fildes", "pid_t", "int32_t", "int64_t", "uint32_t", "uint64_t"), "int"),
    "float": "float", "double": "float", "Py_complex": "complex", "bool": "bool", "str": "str",
    "unicode": "str", "Py_UNICODE": "str", "bytes": "bytes", "PyBytesObject": "bytes", "PyByteArrayObject": "bytearray",
    "Py_buffer": "typing_extensions.Buffer", "object": "Any", "NoneType": "None",
}

#: C source suffixes searched for an extension's sources, in order
CAPI_SOURCE_SUFFIXES: tuple[str, ...] = (".c", ".cc", ".cpp", ".cxx")

#: Most C files read for one extension module
CAPI_MAX_SOURCES = 24
