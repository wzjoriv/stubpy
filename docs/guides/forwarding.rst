Forwarding ``*args`` and ``**kwargs``
=====================================

When a function takes ``*args`` or ``**kwargs`` and passes them on, the caller can supply
whatever the callee accepts. stubpy finds the callee and writes those parameters into the
stub, so editors and type checkers see them. Parameters reached through ``**kwargs`` are
keyword-only and come after the function's own; parameters reached through ``*args`` are
positional-only (see :ref:`forwarding-args`).

Every output below was produced by ``stubpy render <file>``; ``--no-import`` gives the same
parameters (without ``-> None`` on ``__init__``).

Through the MRO: ``super().__init__(**kwargs)``
-----------------------------------------------

.. code-block:: python

   # mro.py
   class Element:
       def __init__(self, id: str = "", hidden: bool = False): ...


   class Styled(Element):
       def __init__(self, fill: str = "none", *, stroke: str = "black", **kwargs):
           super().__init__(**kwargs)


   class Circle(Styled):
       def __init__(self, r: float, **kwargs):
           super().__init__(**kwargs)

.. code-block:: python

   class Element:
       def __init__(self, id: str = '', hidden: bool = False) -> None: ...

   class Styled(Element):
       def __init__(
           self,
           fill: str = 'none',
           *,
           stroke: str = 'black',
           id: str = '',
           hidden: bool = False,
       ) -> None: ...

   class Circle(Styled):
       def __init__(
           self,
           r: float,
           *,
           fill: str = 'none',
           stroke: str = 'black',
           id: str = '',
           hidden: bool = False,
       ) -> None: ...

``Circle`` collects the parameters of every class on the way up. Names the child already
declares are not repeated.

``cls(**kwargs)`` in a class method
-----------------------------------

A class method that forwards into ``cls(...)`` is resolved against ``cls.__init__``.

.. code-block:: python

   # clsfwd.py
   class Base:
       def __init__(self, a: int, b: str = "x"): ...


   class Widget(Base):
       @classmethod
       def create(cls, name: str, **kwargs) -> "Widget":
           return cls(**kwargs)

.. code-block:: python

   class Widget(Base):
       @classmethod
       def create(
           cls,
           name: str,
           *,
           a: int,
           b: str = 'x',
       ) -> Widget: ...

``self.method(**kwargs)``
-------------------------

.. code-block:: python

   class Panel:
       def __init__(self, title: str, border: int = 1): ...

       def configure(self, *, wrap: bool = False, indent: int = 0) -> None: ...

       def update(self, title: str, **kwargs) -> None:
           self.configure(**kwargs)

.. code-block:: python

   class Panel:
       def __init__(self, title: str, border: int = 1) -> None: ...
       def configure(
           self,
           *,
           wrap: bool = False,
           indent: int = 0,
       ) -> None: ...
       def update(
           self,
           title: str,
           *,
           wrap: bool = False,
           indent: int = 0,
       ) -> None: ...

Plain function forwarding
-------------------------

Module-level functions are resolved too, including chains of them.

.. code-block:: python

   # funcs.py
   def connect(host: str, port: int = 80, *, timeout: float = 5.0, ssl: bool = False) -> None: ...


   def fetch(url: str, **kwargs) -> bytes:
       connect("localhost", **kwargs)
       return b""

.. code-block:: python

   def fetch(
       url: str,
       *,
       port: int = 80,
       timeout: float = 5.0,
       ssl: bool = False,
   ) -> bytes: ...

``host`` is missing because the call binds it (``"localhost"``).

Pre-bound arguments with ``*args, **kwargs``
--------------------------------------------

Arguments the call binds are removed from the result. When ``*args`` is forwarded together
with ``**kwargs``, the remaining positional parameters take its place.

.. code-block:: python

   def prebound(*args, **kwargs):
       connect("example.org", *args, **kwargs)

.. code-block:: python

   def prebound(
       port: int = 80,
       *,
       timeout: float = 5.0,
       ssl: bool = False,
   ): ...

``host`` is bound by the call, so ``*args`` becomes ``port``.

.. code-block:: python

   def draw(x: int, y: int, *, color: str = "red") -> None: ...

   def draw_all(*args, **kwargs) -> None:
       draw(*args, **kwargs)

.. code-block:: python

   def draw_all(
       x: int,
       y: int,
       *,
       color: str = 'red',
   ) -> None: ...

Positional-only parameters of a callee that end up behind ``**kwargs`` are promoted to
positional-or-keyword, so the stub stays valid. An explicitly annotated ``*args``
(``*elements: Element``) is kept.

.. _forwarding-args:

Forwarding ``*args``
--------------------

Alone, ``*args`` is expanded into positional-only parameters, because the caller can only
pass them by position. Keyword-only parameters of the callee are not offered, and a typed
``*rest`` in the callee types the caller's ``*args``.

.. code-block:: python

   # pos.py
   def target(a: int, b: str = "x", /, c: float = 1.0, *rest: bytes, k: bool = False) -> None: ...

   def f(*args):
       target(*args)

   def g(x: str, *args):
       target(x, *args)

.. code-block:: python

   def f(
       a: int,
       b: str = 'x',
       c: float = 1.0,
       /,
       *args: bytes,
   ): ...

   def g(
       x: str,
       b: str = 'x',
       c: float = 1.0,
       /,
       *args: bytes,
   ): ...

``k`` is dropped. In ``g`` the call binds ``a`` to ``x``, so ``*args`` starts at ``b``; the
caller's own ``x`` comes before positional-only parameters and becomes positional-only too.

Unpacking is followed like ``f(*args)``; slicing is not:

.. code-block:: python

   # unpack.py
   def target(a: int, b: str = "x", /) -> None: ...

   def f(*args):
       first, *rest = args
       target(first, *rest)

   def h(*args):
       target(*args[1:])

.. code-block:: python

   def f(
       a: int,
       b: str = 'x',
       /,
   ): ...

   def h(*args): ...

The same call shapes work as for ``**kwargs``: ``super().__init__(*args)``, ``cls(*args)``
in a class method, ``self.method(*args)``, plain functions and ``functools.partial``
variables.

.. code-block:: python

   # shapes.py
   class Base:
       def __init__(self, a: int, b: str = "x", /): ...

   class Child(Base):
       def __init__(self, *args):
           super().__init__(*args)

       @classmethod
       def make(cls, *args):
           return cls(*args)

       def run(self, *args):
           self.step(*args)

       def step(self, n: int, m: int = 0, /) -> None: ...

.. code-block:: python

   class Child(Base):
       def __init__(
           self,
           a: int,
           b: str = 'x',
           /,
       ) -> None: ...
       @classmethod
       def make(
           cls,
           a: int,
           b: str = 'x',
           /,
       ): ...
       def run(
           self,
           n: int,
           m: int = 0,
           /,
       ): ...
       def step(
           self,
           n: int,
           m: int = 0,
           /,
       ) -> None: ...

Callees with a text signature resolve too: ``math.atan2(*args)`` gives
``def atan(y, x, /): ...``. An ``@overload``-ed callee gives one ``@overload`` per variant,
each with positional-only parameters:

.. code-block:: python

   @overload
   def ov(a: int, /) -> int: ...
   @overload
   def ov(a: str, b: str, /) -> str: ...
   def ov(*a): ...

   def wrapped(*args):
       return ov(*args)

.. code-block:: python

   @overload
   def wrapped(a: int, /) -> int: ...
   @overload
   def wrapped(
       a: str,
       b: str,
       /,
   ) -> str: ...

``*args`` and ``**kwargs`` can go to different callees; the results combine:

.. code-block:: python

   def pos_only(a: int, b: int, /): ...
   def kw_only(*, k: int): ...

   def both(*args, **kwargs):
       pos_only(*args)
       kw_only(**kwargs)

.. code-block:: python

   def both(
       a: int,
       b: int,
       /,
       *,
       k: int,
   ): ...

``pop`` and ``del``
-------------------

A key the body reads out of ``**kwargs`` with ``.pop(...)`` or removes with ``del`` is
accepted by the function but not forwarded. stubpy lists it as a keyword-only parameter
with the ``pop`` default (``...`` for ``del``), and does not take the callee's version of it.

.. code-block:: python

   def fetch_quiet(url: str, **kw) -> bytes:
       kw.pop("ssl", None)
       return fetch(url, **kw)

.. code-block:: python

   def fetch_quiet(
       url: str,
       *,
       ssl = None,
       port: int = 80,
       timeout: float = 5.0,
   ) -> bytes: ...

``ssl`` is still accepted, with no type, because ``fetch_quiet`` consumes it.

Other callees and call shapes
-----------------------------

* Attribute callees: ``net.connect(**kw)`` after ``from . import net``, ``pkg.sub.f(**kw)``
  after ``import pkg.sub``, at module level or imported inside the function.
* A ``functools.partial`` stored in a variable (``quick = partial(connect, port=8080)``):
  the bound arguments are applied as ``inspect.signature`` does.
* Merged dictionaries: ``inner(**{**defaults, **kwargs, "c": 5})`` forwards ``**kwargs``; keys
  written after ``**kwargs`` (``c``) are fixed by the call and left out.
* A ``functools.wraps`` decorator gives the decorated function the signature of the wrapped
  one.
* Dataclass, ``attrs``, ``NamedTuple`` and ``TypedDict`` constructors: ``Point(**kw)`` expands
  to the fields; ``TypedDict`` keys become keyword-only, optional keys default to ``...``.
  An ``attrs`` class (``@attr.s``, ``@attrs.define``, ``@attr.dataclass``, ...) also gets its
  synthesised ``__init__`` written in its stub: types come from the annotation, ``type=``, a
  literal ``default`` or a builtin ``factory``, ``kw_only`` and ``init=False`` are respected,
  a leading underscore is dropped from the parameter name (or ``alias=`` used), and a
  converter function's annotated input type types the parameter.
* ``**kwargs: Unpack[Options]`` is kept as written in the function's own stub; a caller
  forwarding into it gets the keys of ``Options``. This holds alike for module functions
  and methods (``self.request(**kwargs)``), and when ``Options`` lives in another module or
  is imported under ``if TYPE_CHECKING:``. A function that is itself typed
  ``Unpack[Options]`` but forwards into such a callee gets the callee's keys.
* A function or method whose parameters are exactly ``*args, **kwargs``, passed on unchanged
  to an ``@overload``-ed callee, gets one ``@overload`` per callee variant.
* A decorator typed with ``ParamSpec`` (``(*args: P.args, **kwargs: P.kwargs)`` closing over
  the wrapped function) keeps the wrapped function's signature, even without
  ``functools.wraps``.

Copying with changes
--------------------

``dataclasses.replace(obj, **changes)``, ``copy.replace(obj, **changes)`` (Python 3.13+),
``obj._replace(**changes)`` on a ``NamedTuple`` and ``attrs.evolve(obj, **changes)`` accept
any ``__init__`` field of the object's class. ``**changes`` becomes one optional keyword per
field (``x: int = ...``), leaving out ``init=False`` fields and keywords the call already
sets. It works for ``self`` in a method and for a parameter annotated with the class.

.. code-block:: python

   # replacing.py
   import dataclasses
   from typing import NamedTuple

   @dataclasses.dataclass
   class Point:
       x: int
       y: int = 0
       tag: str = dataclasses.field(default="", init=False)

       def moved(self, **changes):
           return dataclasses.replace(self, **changes)

   def shifted(p: Point, **changes):
       return dataclasses.replace(p, x=1, **changes)

   class Pair(NamedTuple):
       a: int
       b: str = ""

       def with_(self, **changes):
           return self._replace(**changes)

.. code-block:: python

   class Point:
       def moved(
           self,
           *,
           x: int = ...,
           y: int = ...,
       ): ...

   def shifted(
       p: Point,
       *,
       y: int = ...,
   ): ...

   class Pair(NamedTuple):
       def with_(
           self,
           *,
           a: int = ...,
           b: str = ...,
       ): ...

What is not resolved
--------------------

When stubpy cannot find the callee, or the call builds the arguments some other way, the
signature is left as written:

.. code-block:: python

   def untouched(x, **kwargs): ...          # nothing forwarded: unchanged

   def g(a, **kwargs):
       inner(a, **{k: v for k, v in kwargs.items()})   # computed dictionary: unchanged, WARNING

Turn the expansion off
----------------------

``resolve_kwargs = false`` (``--no-resolve-kwargs``) keeps ``**kwargs`` as written;
``resolve_args = false`` (``--no-resolve-args``) does the same for ``*args``. The two are
independent.

.. code-block:: python

   # multi.py
   class Base:
       def __init__(self, a: int, b: int = 0): ...

   class Child(Base):
       def __init__(self, c: str, **kwargs):
           super().__init__(**kwargs)

``stubpy render multi.py --no-resolve-kwargs``:

.. code-block:: python

   class Base:
       def __init__(self, a: int, b: int = 0) -> None: ...

   class Child(Base):
       def __init__(self, c: str, **kwargs) -> None: ...

How it works
------------

When the module is imported, stubpy combines the live classes (for the MRO and the real
signatures) with an AST pass over the source (for the forwarding calls, ``pop`` and
``del``).

With ``--imports none`` (``--no-import``), or when the import fails or is blocked by the
import policy, nothing is imported. One run keeps an index of the harvested sources; names
are followed through imports (relative, absolute within the package, and imports inside the
function), module attributes, aliases and ``partial`` variables; class MROs are linearised
from the source bases. The same call-site rules apply (positional pre-binding, ``pop`` /
``del``, ``cls(...)``, ``type(self)(...)``, ``self.m(...)``, ``super()`` and
``Base.m(self, ...)``), so the result matches the live result wherever the source says enough.
Annotations and defaults written in another module are imported into the stub
(``from .base import Color``) or dropped when they cannot be.

A base class or callee outside the package is read from the source of the installed
package (or its bundled ``.pyi`` or ``<name>-stubs`` package), located without importing it.
Standard-library and builtin callees (``open``, ``subprocess.run``, ``json.dumps``,
``logging.Logger.log`` reached through a typed attribute) resolve in both modes, since
importing the standard library is always allowed. A base that cannot be found stops the
walk. See :doc:`modes` and :doc:`../explanation/architecture`.
