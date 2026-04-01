.. _api_reference:

API Reference
=============

stubpy exposes a minimal public API.  The main entry points for everyday
use are :func:`~stubpy.generator.generate_stub` (single file) and
:func:`~stubpy.generator.generate_package` (whole package).  The
remaining modules are documented here for contributors and for anyone
building on top of stubpy.

.. toctree::
   :maxdepth: 1

   public
   context
   generator
   config
   loader
   diagnostics
   ast_pass
   symbols
   aliases
   annotations
   imports
   resolver
   emitter
