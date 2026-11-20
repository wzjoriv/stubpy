"""
The errors a module load raises, and their one-line descriptions.
"""
from __future__ import annotations


class ModuleLoadError(ImportError):
    """Raised when executing a target module fails; ``cause`` is the original exception.

    Parameters
    ----------
    message : str
        Description of the failure.
    cause : BaseException, optional
        The exception raised while importing. Defaults to None.

    Examples
    --------
    >>> err = ModuleLoadError("boom", ValueError("bad"))
    >>> str(err), err.cause
    ('boom', ValueError('bad'))
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class ModuleReplacedError(ModuleLoadError):
    """Raised when a module replaces its own ``sys.modules`` entry with a non-module object.

    Examples
    --------
    >>> issubclass(ModuleReplacedError, ModuleLoadError)
    True
    """


def _load_error(exc: BaseException) -> BaseException:
    """Return the exception to raise for a failed import: ``SystemExit`` becomes :exc:`ModuleLoadError`."""
    if isinstance(exc, SystemExit):
        return ModuleLoadError(f"SystemExit: {exc.code}", exc)
    return exc


def describe_load_error(exc: BaseException) -> str:
    """Return ``"Type: message"`` for *exc*; :exc:`ModuleLoadError` messages already have that form.

    Parameters
    ----------
    exc : BaseException
        The exception raised while loading.

    Returns
    -------
    str
        A one-line description.

    Examples
    --------
    >>> describe_load_error(ValueError("bad value"))
    'ValueError: bad value'
    >>> describe_load_error(ModuleLoadError("SystemExit: 1"))
    'SystemExit: 1'
    """
    if isinstance(exc, ModuleLoadError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"
