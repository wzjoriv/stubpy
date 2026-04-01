.. _api_resolver:

stubpy.resolver
===============

.. automodule:: stubpy.resolver
   :no-members:

.. rubric:: Class-method resolution

.. autofunction:: stubpy.resolver.resolve_params

.. rubric:: Module-level function resolution

.. autofunction:: stubpy.resolver.resolve_function_params

.. rubric:: Shared helpers

.. autofunction:: stubpy.resolver._normalise_kind
.. autofunction:: stubpy.resolver._merge_concrete_params
.. autofunction:: stubpy.resolver._finalise_variadics
.. autofunction:: stubpy.resolver._enforce_signature_validity

.. rubric:: Resolution strategies

:func:`resolve_params` (class methods) applies three strategies in order:

1. **No variadics** — return own parameters unchanged.
2. **cls()-call detection** — if the body contains ``cls(..., **kwargs)``,
   resolve against ``cls.__init__``.  Hardcoded keyword names are excluded.
3. **MRO walk** — collect concrete params from ancestors until all variadics
   are resolved or the MRO is exhausted.

:func:`resolve_function_params` (standalone functions) applies:

1. **No variadics** — return own parameters unchanged.
2. **No targets** — return own parameters unchanged (variadics preserved).
3. **Target resolution** — look each name up in the module namespace and merge
   its concrete parameters.  Recursive for chained forwarding; cycle-safe.
4. **Default-ordering enforcement** — absorbed non-default params following a
   defaulted own-param are promoted to ``KEYWORD_ONLY``.

.. rubric:: Parameter ordering (both resolvers)

1. The function/method's own concrete parameters (source order).
2. Parameters from the first resolved target / ancestor.
3. Parameters from further targets / ancestors, in resolution order.
4. ``*args`` — placed before keyword-only params and before ``**kwargs``.
5. Residual ``**kwargs`` — appended last if still unresolved.

.. rubric:: Positional-only parameters

``POSITIONAL_ONLY`` parameters absorbed via ``**kwargs`` are promoted to
``POSITIONAL_OR_KEYWORD`` by :func:`_normalise_kind` — a positional-only
param passed through ``**kwargs`` must be supplied by keyword.

.. rubric:: Default-ordering rule

:func:`_enforce_signature_validity` promotes any non-default parameter that
follows a defaulted parameter in the positional portion to ``KEYWORD_ONLY``.
This is correct semantically: absorbed params arrive via ``**kwargs`` and are
keyword arguments in practice.
