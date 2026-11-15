Hints
=====

Introspection cannot see everything: JIT-compiled functions, callables built at runtime and
C-implemented functions have no useful signature. The decorators in :mod:`stubpy.hint` tell
stubpy what to write.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Decorator
     - Effect on the stub
   * - ``@hint.signature("(x: int) -> str")``
     - Replaces the whole signature. Text is everything after the name, starting with ``(``.
       Methods include ``self`` / ``cls``.
   * - ``@hint.returns("list[int]")``
     - Replaces only the return annotation; the parameters are kept.
   * - ``@hint.ignore``
     - Leaves the function, method or class out of the stub.

Each decorator only sets an attribute on the object and returns it unchanged, so the cost at
runtime is one assignment. stubpy also reads the decorators from the source, so they work in
``ast`` mode and on objects that cannot take attributes. The decorators never appear in the
stub.

Example
-------

.. code-block:: python

   # hinted.py
   from stubpy import hint

   @hint.signature("(x: float, y: float) -> float")
   def dist(x, y):
       return (x * x + y * y) ** 0.5

   @hint.returns("list[int]")
   def load(path: str):
       return []

   @hint.ignore
   def _debug_dump(): ...

   def plain(a, b=1): ...

``stubpy render hinted.py``:

.. code-block:: python

   def dist(x: float, y: float) -> float: ...

   def load(path: str) -> list[int]: ...

   def plain(a, b: int = 1): ...

``hint.signature`` and ``hint.returns`` raise ``TypeError`` when given a non-string, and
``hint.signature`` raises ``ValueError`` when the text does not start with ``(``.

Keeping stubpy a development dependency
---------------------------------------

Your package should not need stubpy at runtime just for the decorators. Fall back to no-ops
when it is not installed:

.. code-block:: python

   try:
       from stubpy import hint
   except ImportError:
       class hint:
           signature = returns = staticmethod(lambda _text: lambda obj: obj)
           ignore = staticmethod(lambda obj: obj)

stubpy finds the decorators by their ``hint.`` prefix in the source, so keep the name
``hint``.

.. note::

   stubpy recognises the ``try: from stubpy import hint`` / ``except ImportError:`` fallback
   pattern and leaves the fallback ``class hint`` out of the stub in every mode.

Leaving out a whole file
------------------------

A ``# stubpy: ignore`` comment at the top of a source file leaves its contents out of the
stub.
