.. _api_emitter:

stubpy.emitter
==============

.. automodule:: stubpy.emitter
   :no-members:

.. autofunction:: stubpy.emitter.generate_class_stub
.. autofunction:: stubpy.emitter.generate_method_stub
.. autofunction:: stubpy.emitter.methods_defined_on
.. autofunction:: stubpy.emitter.insert_kw_separator

.. rubric:: Formatting rules

**Inline** (≤ 2 non-self/cls parameters)::

    def area(self) -> float: ...
    def scale(self, sx: float, sy: Optional[float] = None) -> Element: ...

**Multi-line** (> 2 non-self/cls parameters), each param on its own line
with a trailing comma::

    def __init__(
        self,
        width: float,
        height: float,
        depth: float = 1.0,
    ) -> None: ...

Trailing commas make diffs cleaner — adding or removing a parameter
changes exactly one line.

.. rubric:: Public dunders

Only the methods listed in the internal ``_PUBLIC_DUNDERS`` set are
included in stubs. Internal Python machinery names (``__dict__``,
``__weakref__``, ``__class__``, etc.) are omitted.
