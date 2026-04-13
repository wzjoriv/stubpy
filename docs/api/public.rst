.. _api_public:

Public API reference
====================

All names exported from the top-level :mod:`stubpy` package form the stable
public interface.  Everything else is internal and may change between minor
versions.

.. rubric:: Core entry points

.. autosummary::
   :nosignatures:

   stubpy.generator.generate_stub
   stubpy.generator.generate_package
   stubpy.generator.PackageResult

See :ref:`api_generator` for full documentation.

.. rubric:: Configuration

.. autosummary::
   :nosignatures:

   stubpy.context.StubConfig
   stubpy.context.StubContext
   stubpy.context.ExecutionMode
   stubpy.context.AliasEntry
   stubpy.config.load_config
   stubpy.config.find_config_file

See :ref:`api_context` and :ref:`api_config` for full documentation.

.. rubric:: Diagnostics

.. autosummary::
   :nosignatures:

   stubpy.diagnostics.DiagnosticCollector
   stubpy.diagnostics.Diagnostic
   stubpy.diagnostics.DiagnosticLevel
   stubpy.diagnostics.DiagnosticStage

See :ref:`api_diagnostics` for full documentation.

.. rubric:: Stub emitters

.. autosummary::
   :nosignatures:

   stubpy.emitter.generate_class_stub
   stubpy.emitter.generate_function_stub
   stubpy.emitter.generate_variable_stub
   stubpy.emitter.generate_alias_stub
   stubpy.emitter.generate_overload_group_stub

See :ref:`api_emitter` for full documentation.

.. rubric:: Annotation handling

.. autosummary::
   :nosignatures:

   stubpy.annotations.annotation_to_str
   stubpy.annotations.format_param
   stubpy.annotations.register_annotation_handler

See :ref:`api_annotations` for full documentation.

.. rubric:: Docstring type inference

.. autosummary::
   :nosignatures:

   stubpy.docstring.parse_docstring_types
   stubpy.docstring.DocstringTypes

See :ref:`api_docstring` for full documentation.

.. rubric:: Incremental stub merge

.. autosummary::
   :nosignatures:

   stubpy.stub_merge.merge_stubs
   stubpy.stub_merge.wrap_generated
   stubpy.stub_merge.read_and_merge

See :ref:`api_stub_merge` for full documentation.
