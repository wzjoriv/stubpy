Inferred types
==============

stubpy writes the types the source and the runtime state. Where the source has none, it
fills in only what is certain from the code; types read from docstrings need
``--infer-types`` (``infer_types = true``) unless they come from a forwarded callee.

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - What
     - When
     - Source of the type
   * - Parameter with a literal default
     - always
     - The literal's type: ``n=3`` becomes ``n: int = 3``. ``None`` stays untyped.
   * - Keyword forwarded from an unannotated callee
     - always (imported modules)
     - The callee's literal default, else its NumPy, Google or Sphinx docstring
       (for ``__init__``, also the class docstring), when that type is built from builtins
       and ``typing`` names only.
   * - Unannotated return
     - always
     - The safe rules below.
   * - The function's own parameters and return
     - ``--infer-types``
     - Its docstring.

Safe return types
-----------------

A function without a return annotation gets one only when every ``return`` agrees on a
type that cannot be wrong:

* no ``return`` with a value: ``-> None`` (stub bodies, generators and functions that end
  in ``raise`` excepted);
* every ``return`` a literal of one type: ``return 1`` / ``return 2`` give ``-> int``;
* ``return self`` and ``return cls(...)`` / ``return type(self)(...)``: ``-> Self`` when
  ``target_python`` is 3.11 or later, else the class name;
* ``return Name(...)`` where ``Name`` is a class of the module: ``-> Name``;
* f-strings and ``str`` methods of a string literal (``", ".join(x)``): ``-> str``;
* builtins whose result type is fixed: ``len`` / ``hash`` → ``int``, ``repr`` / ``str`` →
  ``str``, ``isinstance`` / ``hasattr`` → ``bool``, and so on;
* ``not x`` and ``is`` / ``is not`` / ``in`` / ``not in`` tests: ``-> bool``.

Nothing is inferred when two returns disagree, when the body can fall off the end after a
``return`` value (an implicit ``None``), for ``==`` and ``<`` comparisons (NumPy arrays
return arrays), when a name the rule relies on is rebound in the function, or when the
function has a decorator other than ``staticmethod``, ``classmethod``, ``property``,
``functools.cache`` / ``lru_cache`` / ``cached_property``, ``override`` or ``final``.

These rules apply by default because they read only the code and are exact for it; a
written annotation, a ``@hint.returns`` or a protocol type such as ``__len__ -> int`` always
wins. Docstring types are prose that may be stale, so for the function's own signature they
stay behind ``--infer-types``.

.. code-block:: python

   class Builder:
       def chain(self):
           return self

       def label(self):
           return f"b{self.n}"

       def reset(self):
           self.n = 0

       def pick(self, other):
           return other

.. code-block:: python

   class Builder:
       def chain(self) -> Builder: ...   # Self with target_python = "3.11"
       def label(self) -> str: ...
       def reset(self) -> None: ...
       def pick(self, other): ...

Aliases from private modules
----------------------------

A type alias defined in a private module (one with a ``_``-prefixed part, such as
``pkg._types``) is written as its value when the module does not list it in ``__all__``:
users of the stub cannot import it by name.

.. code-block:: python

   # pkg/_types.py
   VerifyType = bool | str

   # pkg/api.py
   from . import _types as _t

   def get(url: str, verify: _t.VerifyType = True) -> None: ...

.. code-block:: python

   def get(url: str, verify: bool | str = True) -> None: ...

Aliases from public modules, and aliases a private module exports through ``__all__``
(a shared ``_typing`` module, say), keep their names and are imported. ``NewType`` and
``type`` statements always keep their names. The rewrite needs the module to be imported;
with ``--no-import`` the annotation is copied as written.
