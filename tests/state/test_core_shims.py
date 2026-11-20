"""The old ``stubpy.core`` homes of the run state re-export the same objects."""
import stubpy
import stubpy.core.context as core_context
import stubpy.core.diagnostics as core_diagnostics
import stubpy.extend as extend
from stubpy.state import context, diagnostics


def test_core_context_is_an_alias():
    assert core_context.StubContext is context.StubContext
    assert core_context.AliasEntry is context.AliasEntry


def test_core_diagnostics_is_an_alias():
    for name in ("Diagnostic", "DiagnosticCollector", "Level", "Stage"):
        assert getattr(core_diagnostics, name) is getattr(diagnostics, name)


def test_public_names_are_unchanged():
    assert stubpy.Diagnostic is diagnostics.Diagnostic and stubpy.Level is diagnostics.Level
    assert extend.StubContext is context.StubContext and extend.Stage is diagnostics.Stage
