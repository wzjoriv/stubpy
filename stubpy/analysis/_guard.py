"""A ``sys.meta_path`` guard that refuses imports outside the run's :class:`~stubpy.config.ImportPolicy`."""
from __future__ import annotations

import contextlib
import importlib.abc
import sys
from collections.abc import Iterator
from typing import Any


class ImportBlockedError(ImportError):
    """An import the policy refused; *module* is the first module that was blocked."""

    def __init__(self, module: str) -> None:
        super().__init__(f"blocked by stubpy import policy: {module}", name=module)
        self.module = module


class PolicyFinder(importlib.abc.MetaPathFinder):
    """Raises :exc:`ImportBlockedError` for every module the policy does not allow; *blocked* lists them."""

    def __init__(self, policy: Any) -> None:
        self.policy = policy
        self.blocked: list[str] = []

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname in sys.modules or self.policy.allows(fullname):
            return None
        self.blocked.append(fullname)
        raise ImportBlockedError(fullname)


@contextlib.contextmanager
def import_guard(policy: Any) -> Iterator[PolicyFinder | None]:
    """Install a :class:`PolicyFinder` first on ``sys.meta_path`` for the block; nothing for an unrestricted policy."""
    if policy is None or policy.unrestricted:
        yield None
        return
    finder = PolicyFinder(policy)
    sys.meta_path.insert(0, finder)
    try:
        yield finder
    finally:
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(finder)
