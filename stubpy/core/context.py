"""
Compatibility alias: the run context now lives in :mod:`stubpy.state.context`.
"""
from stubpy.state.context import AliasEntry, StubContext

__all__ = ["AliasEntry", "StubContext"]
