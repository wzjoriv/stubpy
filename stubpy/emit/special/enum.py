"""
Enum stubs: hide Python's internal enum hooks.
"""
from __future__ import annotations

ENUM_PRIVATE_METHODS: frozenset[str] = frozenset({
    "_generate_next_value_", "_missing_", "_new_member_",
    "_member_type_", "_value_repr_", "_iter_member_",
    "_check_value_",
})


def public_enum_methods(method_names: list[str]) -> list[str]:
    """Drop enum implementation hooks from *method_names*."""
    return [m for m in method_names if m not in ENUM_PRIVATE_METHODS]
