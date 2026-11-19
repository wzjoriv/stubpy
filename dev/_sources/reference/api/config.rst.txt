Configuration
=============

.. currentmodule:: stubpy

.. autoclass:: Config
   :members: from_dict, replace, may_import, import_policy
   :member-order: bysource

The style enums are the types of the ``union_style`` and ``alias_style`` fields. They are not
exported at the top level; import them from ``stubpy.config``, or pass the plain strings.

.. autoclass:: stubpy.config.UnionStyle
   :members:
   :undoc-members:

.. autoclass:: stubpy.config.AliasStyle
   :members:
   :undoc-members:

.. autoclass:: stubpy.config.VersionBranches
   :members:
   :undoc-members:

``Config.imports`` and ``Config.deny_imports`` decide which modules stubpy may import;
:attr:`Config.import_policy` returns them as an :class:`~stubpy.config.ImportPolicy`.

.. autoclass:: stubpy.config.ImportPolicy
   :members: unrestricted, allows

``Config.docstrings`` holds the stubs that ``stubpy docstrings`` acts on when it gets no
arguments. A mapping coerces to this class.

.. autoclass:: stubpy.config.DocstringTargets
   :members:
   :undoc-members:
