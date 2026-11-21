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
    constants : dict of str to str
        Module attributes the init code adds (``PyModule_AddIntConstant`` and the like) to their type.
    exceptions : dict of str to str
        Exception classes made with ``PyErr_NewException`` to the name of their builtin base.
    docs : dict of str to str
        ``function`` or ``Class.method`` to the docstring in its ``PyMethodDef`` row.
    """
    signatures: dict[str, Signature] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
    classes: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    exceptions: dict[str, str] = field(default_factory=dict)
    docs: dict[str, str] = field(default_factory=dict)
