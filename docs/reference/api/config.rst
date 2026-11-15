Configuration
=============

.. currentmodule:: stubpy

.. autoclass:: Config
   :members: from_dict, replace
   :member-order: bysource

.. autoclass:: Mode
   :members:
   :undoc-members:

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
