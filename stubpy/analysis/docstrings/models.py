"""The :class:`DocstringTypes` result of parsing one docstring."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocstringTypes:
    """Parameter and return types found in one docstring.

    Attributes
    ----------
    params : dict of str to str
        Parameter name to type string.
    returns : str or None
        Return type string, if any.
    """
    params: dict[str, str] = field(default_factory=dict)
    returns: str | None = None

    def is_empty(self) -> bool:
        """Return ``True`` when no type information was found."""
        return not self.params and self.returns is None

    def merge(self, other: DocstringTypes) -> DocstringTypes:
        """Return a merged result; *self* wins and *other* fills the gaps."""
        merged_params = dict(other.params)
        merged_params.update(self.params)
        return DocstringTypes(
            params=merged_params,
            returns=self.returns if self.returns is not None else other.returns,
        )
