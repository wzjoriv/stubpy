What the body does with the arguments
=====================================

Between receiving ``*args`` / ``**kwargs`` and passing them on (see :doc:`forwarding`), a
function body often takes some keys out, reads others, picks the callee from a literal, or
copies an object with changes. Each changes what callers may pass; stubpy reflects it in
the signature.

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

Reading a key or an index
-------------------------

A key read but left in ``**kwargs`` (``kwargs["k"]``, ``kwargs.get("k", d)``) is also a
keyword-only parameter. Under ``**kwargs: T`` its type is ``T`` (``T | None`` for a ``.get``
without a default); otherwise a literal ``.get`` default gives its type, else the type is
``Any``. A literal default is kept either way. ``kwargs["k"]`` makes it required, unless the body also tests
``"k" in kwargs`` (then ``= ...``). A key a forwarded callee already takes keeps the callee's
version. ``args[i]`` reads become positional-only parameters ``args_0`` ... ``args_i`` before an
``*args`` that is not forwarded. An annotated ``*args`` and ``**kwargs: Unpack[...]`` are left
as written.

.. code-block:: python

   def plot(*args, **kwargs):
       x = args[0]
       title = kwargs.get("title", "")
       return draw(**kwargs)          # draw(*, color: str = "k")

.. code-block:: python

   def plot(
       args_0: Any,
       /,
       *args,
       color: str = 'k',
       title: str = '',
   ): ...

One ``@overload`` per literal branch
------------------------------------

When the callee depends on a parameter compared against literals, each branch gets an
``@overload`` with the parameter narrowed to ``Literal[...]``, that branch's callee
parameters and, when the branch returns the call to a class or annotated function, its
return type. A last variant keeps the general signature (the union of every branch). The
selector can be tested with ``if`` / ``elif`` (``==``, ``is``, ``in (...)``, ``or``), a
``match`` with literal ``case`` patterns (``"a" | "b"`` too), or used as the key into a dict
of callees, inline or at module level. The dict form needs a ``Literal`` annotation (or
``Enum`` member keys); a ``str`` key may be anything, so it keeps ``**kwargs`` open.

.. code-block:: python

   def make(kind: Literal["circle", "rect"], **kwargs) -> Shape:
       if kind == "circle":
           return Circle(**kwargs)    # Circle(r: float)
       elif kind == "rect":
           return Rect(**kwargs)      # Rect(width: float, height: float)
       raise ValueError(kind)

.. code-block:: python

   @overload
   def make(kind: Literal['circle'], *, r: float) -> Circle: ...
   @overload
   def make(kind: Literal['rect'], *, width: float, height: float) -> Rect: ...
   @overload
   def make(kind: Literal['circle', 'rect'], *, r: float, width: float, height: float) -> Shape: ...

Statements after an ``if`` chain whose every branch returns or raises count as its ``else``.
The ``if`` / ``match`` may sit at the top of the body or inside the body of a ``try``, ``with``,
``for`` or ``while``, as long as that block holds every forwarding call of the function (none
in an ``except``, ``else``, ``finally`` or elsewhere); otherwise the plain union is kept.

The registry can also be a class attribute, read as ``cls.registry[kind]``,
``self.registry[kind]`` or ``type(self).registry[kind]``: a dict literal in the class body,
or a name bound to a module-level dict (``registry = REGISTRY``). The same ``Literal`` rule
applies, so ``build(cls, kind: str, **kwargs)`` keeps ``**kwargs`` open while
``kind: Literal["circle", "rect"]`` gets one variant per key.

A selector that is not a parameter (a global, or an attribute such as ``self.kind`` even when
typed ``Literal`` / ``Enum``) gets no ``@overload``: the caller does not pass it, so no variant
could narrow anything the caller writes. The function keeps one signature taking the union of
every branch's parameters, which accepts every valid call.

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

