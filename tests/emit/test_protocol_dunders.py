"""Protocol dunders get their fixed types where the source leaves them out, and keep the ones it gives."""
from __future__ import annotations

import pytest

from tests.conftest import make_stub_ctx

SOURCE = '''
class Box:
    def __init__(self, size): self.size = size
    def __init_subclass__(cls, **kwargs): pass
    def __eq__(self, other): return True
    def __ne__(self, other): return False
    def __lt__(self, other): return True
    def __hash__(self): return 0
    def __len__(self): return 0
    def __bool__(self): return True
    def __repr__(self): return ""
    def __str__(self): return ""
    def __format__(self, spec): return ""
    def __bytes__(self): return b""
    def __int__(self): return 0
    def __float__(self): return 0.0
    def __index__(self): return 0
    def __contains__(self, item): return True
    def __setattr__(self, name, value): pass
    def __delattr__(self, name): pass
    def __setitem__(self, key, value): pass
    def __delitem__(self, key): pass
    def __iter__(self): return iter(())

class Typed:
    def __eq__(self, other: "Typed") -> "Typed": return self
    def __len__(self) -> "Size": return 0
    def __format__(self, spec: int) -> bytes: return b""
'''

EXPECTED = [
    "def __init__(self, size) -> None: ...",
    "def __init_subclass__(cls, **kwargs) -> None: ...",
    "def __eq__(self, other: object) -> bool: ...",
    "def __ne__(self, other: object) -> bool: ...",
    "def __lt__(self, other) -> bool: ...",
    "def __hash__(self) -> int: ...",
    "def __len__(self) -> int: ...",
    "def __bool__(self) -> bool: ...",
    "def __repr__(self) -> str: ...",
    "def __str__(self) -> str: ...",
    "def __format__(self, spec: str) -> str: ...",
    "def __bytes__(self) -> bytes: ...",
    "def __int__(self) -> int: ...",
    "def __float__(self) -> float: ...",
    "def __index__(self) -> int: ...",
    "def __contains__(self, item) -> bool: ...",
    "def __setattr__(self, name, value) -> None: ...",
    "def __delattr__(self, name) -> None: ...",
    "def __setitem__(self, key, value) -> None: ...",
    "def __delitem__(self, key) -> None: ...",
    "def __iter__(self): ...",
]


@pytest.mark.parametrize("imports", ["all", "none"])
def test_missing_protocol_types_are_filled(imports):
    stub, _ = make_stub_ctx(SOURCE, imports=imports)
    for line in EXPECTED:
        assert line in stub, line


@pytest.mark.parametrize("imports", ["all", "none"])
def test_written_types_are_kept(imports):
    stub, _ = make_stub_ctx(SOURCE, imports=imports)
    typed = stub[stub.index("class Typed"):]
    assert "other: Typed" in typed and "-> Typed" in typed
    assert "-> Size" in typed
    assert "spec: int) -> bytes" in typed


def test_module_functions_are_untouched():
    stub, _ = make_stub_ctx("def __eq__(a, b): return True\n")
    assert "def __eq__(a, b): ..." in stub
