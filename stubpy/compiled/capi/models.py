"""
What the C sources of a C API extension say about its Python-visible callables and attributes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..signatures import Signature


@dataclass
class CModule:
    """The signatures and attribute types read from an extension's C sources.

    Attributes
    ----------
    signatures : dict of str to Signature
        ``function`` or ``Class.method`` (``Class.__init__`` for ``tp_init``) to its
        signature, without the receiver; a ``(*args, **kwargs)`` signature only carries a
        return type.
    attributes : dict of str to str
        ``Class.name`` of a ``PyGetSetDef`` or ``PyMemberDef`` entry to its Python type.
    classes : dict of str to str
        The C variable of each static type object to its class name.
    """
    signatures: dict[str, Signature] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
    classes: dict[str, str] = field(default_factory=dict)
