.. _api_resolver:

stubpy.resolver
===============

.. automodule:: stubpy.resolver
   :no-members:

.. autofunction:: stubpy.resolver.resolve_params

.. rubric:: Resolution strategies

:func:`resolve_params` applies three strategies in order:

1. **No variadics** — return own parameters unchanged.
2. **@classmethod cls() detection** — AST analysis; resolves ``**kwargs``
   against ``cls.__init__``. Hardcoded arguments are excluded.
3. **MRO walk** — collect concrete params from each ancestor until all
   variadics are resolved or the MRO is exhausted.

.. rubric:: Parameter ordering

1. The method's own concrete parameters (original order)
2. Parameters from the first MRO ancestor that defines the method
3. Parameters from further ancestors, in MRO order
4. Preserved ``*args`` (if explicitly typed or unresolvable) — always
   placed **before** any keyword-only params and before ``**kwargs``
5. Residual ``**kwargs`` (if the chain was never fully resolved)

.. rubric:: \*args preservation

A ``*args`` parameter is kept when either:

- The MRO walk could not resolve it (``still_var_pos`` remains ``True``).
- The ``*args`` carries an explicit annotation (e.g.
  ``*elements: Element``), indicating a typed variadic.

In both cases ``*args`` is inserted before the first keyword-only
parameter **and** before any trailing ``**kwargs``, so the emitted
signature is always syntactically valid Python.

.. rubric:: Positional-only parameters

When a parent method has ``POSITIONAL_ONLY`` parameters (declared with
``def f(a, b, /, c)``), those parameters are normally preserved with
``POSITIONAL_ONLY`` kind in the child's own signature.

However, when they are absorbed by a child's ``**kwargs``, they are
promoted to ``POSITIONAL_OR_KEYWORD`` in the merged result.  A
positional-only parameter passed through ``**kwargs`` can be supplied by
keyword, so emitting it as positional-only in the child stub would
produce an invalid ``/`` at the wrong location.  The internal
``_normalise_kind`` helper handles this promotion.
