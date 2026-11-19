"""
The :class:`DocstringTypes` result of parsing one docstring.
"""
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

    Examples
    --------
    >>> DocstringTypes(params={"x": "int"}, returns="str").is_empty()
    False
    """
    params: dict[str, str] = field(default_factory=dict)
    returns: str | None = None

    def is_empty(self) -> bool:
        """Return ``True`` when no type information was found.

        Returns
        -------
        bool
            Whether there are neither parameter types nor a return type.

        Examples
        --------
        >>> DocstringTypes().is_empty()
        True
        """
        return not self.params and self.returns is None

    def merge(self, other: DocstringTypes) -> DocstringTypes:
        """Return a merged result; *self* wins and *other* fills the gaps.

        Parameters
        ----------
        other : DocstringTypes
            The result to take missing entries from.

        Returns
        -------
        DocstringTypes
            A new object; neither input is modified.

        Examples
        --------
        >>> a = DocstringTypes({"x": "int"})
        >>> b = DocstringTypes({"x": "str", "y": "float"}, returns="bool")
        >>> merged = a.merge(b)
        >>> merged.params, merged.returns
        ({'x': 'int', 'y': 'float'}, 'bool')
        """
        merged_params = dict(other.params)
        merged_params.update(self.params)
        return DocstringTypes(
            params=merged_params,
            returns=self.returns if self.returns is not None else other.returns,
        )
