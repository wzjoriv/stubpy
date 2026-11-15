``**kwargs`` and ``*args``
==========================

When a function takes ``**kwargs`` and forwards it, the caller can pass whatever the callee
accepts. stubpy finds the callee and writes those parameters into the stub, so editors and type
checkers see them. The expanded parameters are keyword-only and come after the function's own.

Every output below was produced by ``stubpy render <file>``; ``--mode ast`` gives the same
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

Positional pre-binding and ``*args``
------------------------------------

Arguments the call binds are removed from the result. When ``*args`` is forwarded, the
remaining positional parameters take its place.

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
* ``*args`` forwarded to positional-only parameters keeps them positional-only when nothing
  comes before them (``def f(*args)`` calling ``g(a, b, /)`` stubs as ``f(a, b, /)``). A call
  that forwards only ``*args`` does not offer the callee's keyword-only parameters.
* Dataclass, ``NamedTuple`` and ``TypedDict`` constructors: ``Point(**kw)`` expands to the
  fields; ``TypedDict`` keys become keyword-only, optional keys default to ``...``.
* ``**kwargs: Unpack[Options]`` is kept as written in the function's own stub; a caller
  forwarding into it gets the keys of ``Options``.
* A function or method whose parameters are exactly ``*args, **kwargs``, passed on unchanged
  to an ``@overload``-ed callee, gets one ``@overload`` per callee variant.
* A decorator typed with ``ParamSpec`` (``(*args: P.args, **kwargs: P.kwargs)`` closing over
  the wrapped function) keeps the wrapped function's signature, even without
  ``functools.wraps``.

What is not resolved
--------------------

When stubpy cannot find the callee, or the call builds the dictionary some other way, the
signature is left as written:

.. code-block:: python

   def untouched(x, **kwargs): ...          # nothing forwarded: unchanged

   def g(a, **kwargs):
       inner(a, **{k: v for k, v in kwargs.items()})   # computed dictionary: unchanged, WARNING

Turn the expansion off
----------------------

``resolve_kwargs = false`` (``--no-resolve-kwargs``) keeps ``**kwargs`` as written;
``resolve_args = false`` (``--no-resolve-args``) does the same for ``*args``.

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

In ``runtime`` mode stubpy combines the live classes (for the MRO and the real
signatures) with an AST pass over the source (for the forwarding calls, ``pop`` and
``del``).

In ``ast`` mode nothing is imported. One run keeps an index of the harvested sources; names
are followed through imports (relative, absolute within the package, and imports inside the
function), module attributes, aliases and ``partial`` variables; class MROs are linearised
from the source bases. The same call-site rules apply (positional pre-binding, ``pop`` /
``del``, ``cls(...)``, ``type(self)(...)``, ``self.m(...)``, ``super()`` and
``Base.m(self, ...)``), so the result matches ``runtime`` wherever the source says enough.
Annotations and defaults written in another module are imported into the stub
(``from .base import Color``) or dropped when they cannot be. A base outside the package is
skipped when it is a standard-library class without the method, and stops the walk
otherwise. See :doc:`../explanation/architecture`.
