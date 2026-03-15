.. _api_aliases:

stubpy.aliases
==============

.. automodule:: stubpy.aliases
   :no-members:

.. autofunction:: stubpy.aliases.build_alias_registry

.. rubric:: What counts as a type alias?

The internal ``_is_type_alias`` predicate accepts:

- **PEP 604 unions** — ``str | int | float`` (:class:`types.UnionType`)
- **Subscripted typing generics** — ``List[str]``, ``Optional[int]``,
  ``Literal["a", "b"]``, ``Tuple[float, float]`` (any object with a
  non-empty ``__args__``)

It rejects plain classes, module objects, ``None``, and bare
unsubscripted aliases such as ``List`` or ``Optional`` (no ``__args__``).

.. rubric:: Discovery mechanism

:func:`build_alias_registry` scans the *parent module's* namespace for
sub-module attributes.  Only sub-modules imported via ``from pkg import
types`` (not individual names like ``from pkg.types import Length``) are
scanned, preserving author intent.
