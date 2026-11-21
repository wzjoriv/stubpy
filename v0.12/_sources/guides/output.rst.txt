Output style
============

A few options change how the stub is written, not what it contains. Each is a key of
:doc:`configuration` and a command-line flag.

Style options
-------------

``union_style`` and ``alias_style`` change how unions and alias declarations are written, with
or without the import.

.. code-block:: python

   # aliases.py
   from typing import TypeAlias, Optional, Union

   Length: TypeAlias = str | float | int

   class Box:
       def __init__(self, w: Length, h: Optional[Length] = None, tag: Union[str, None] = None): ...

``stubpy render aliases.py`` (the defaults):

.. code-block:: python

   from typing import TypeAlias

   Length: TypeAlias = str | float | int

   class Box:
       def __init__(
           self,
           w: Length,
           h: Length | None = None,
           tag: str | None = None,
       ) -> None: ...

``stubpy render aliases.py --union-style legacy --alias-style pep695``:

.. code-block:: python

   from typing import Optional, Union

   type Length = Union[str, float, int]

   class Box:
       def __init__(
           self,
           w: Length,
           h: Optional[Length] = None,
           tag: Optional[str] = None,
       ) -> None: ...

.. note::

   Annotations that name an alias (``Length``, ``types.Length``) keep the alias name with or
   without the import; the style applies to the alias declaration itself. See :doc:`modes`.

Deprecated ``typing`` aliases are always written in their modern form: ``List[int]`` becomes
``list[int]`` (likewise ``Dict``, ``Set``, ``FrozenSet``, ``Tuple``, ``Type``),
``ContextManager[str]`` becomes ``AbstractContextManager[str]`` from ``contextlib``, and
``Callable``, ``Iterator``, ``Mapping``, ``Sequence`` and the other abstract collections are
imported from ``collections.abc`` (``Pattern`` and ``Match`` from ``re``). Names a module
defines itself or imports from another package are left alone.

Version and platform branches
-----------------------------

Module-level and class-level ``if`` statements whose tests only compare ``sys.version_info``
(``>=``, ``<``, slices such as ``sys.version_info[:2]``) or ``sys.platform`` (``==``, ``!=``,
``startswith``), combined with ``and``, ``or`` and ``not``, are copied into the stub with
their ``elif`` and ``else`` branches, as typeshed writes them. Each branch holds the stubs of
the names it defines, and the imports it needs.

.. code-block:: python

   # compat.py
   import sys

   if sys.version_info >= (3, 11):
       from typing import Self
   else:
       from typing_extensions import Self

   if sys.platform == "win32":
       DEFAULT_SHELL = "cmd.exe"
   else:
       DEFAULT_SHELL = "/bin/sh"


   class Path:
       def joined(self, part: str) -> Self: ...

       if sys.version_info >= (3, 12):
           def walk(self) -> list[Self]: ...

``stubpy render compat.py``:

.. code-block:: python

   import sys

   if sys.version_info >= (3, 11):
       from typing import Self
   else:
       from typing_extensions import Self

   if sys.platform == 'win32':
       DEFAULT_SHELL: str
   else:
       DEFAULT_SHELL: str

   class Path:
       def joined(self, part: str) -> Self: ...

       if sys.version_info >= (3, 12):
           def walk(self) -> list[Self]: ...

The imported module only holds the branch the running interpreter took: that
branch is introspected as usual, the others are stubbed from the source. PEP 695 syntax inside
a branch (``def f[T]``, ``class C[T]``, ``type X[T] = ...``) is rewritten with ``TypeVar``,
``Generic`` and ``TypeAlias`` so the stub still parses on Python 3.10. ``if TYPE_CHECKING:``
and other tests (``if HAS_NUMPY:``) are unchanged: the ``TYPE_CHECKING`` side is stubbed, and
both sides of an unknown test are merged.

``--version-branches resolve`` (``version_branches = "resolve"``) keeps only the branch the
running interpreter takes:

.. code-block:: python

   from typing import Self

   DEFAULT_SHELL: str

   class Path:
       def joined(self, part: str) -> Self: ...
