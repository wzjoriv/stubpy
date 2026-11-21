def np_multi(x, y, scale=1.0, names=None):
    """Numpy.

    Parameters
    ----------
    x, y : int
        Coordinates.
    scale : float, optional
        Factor.
    names : list of str, optional
        Labels.

    Returns
    -------
    tuple of (int, int)
        Point.
    """

def np_array(a, mode="fast"):
    """
    Parameters
    ----------
    a : array_like
        Input.
    mode : {'fast', 'slow'}
        Mode.

    Returns
    -------
    ndarray
    """

def g_basic(path, retries=3, *args, **kwargs):
    """Google.

    Args:
        path (str): File.
        retries (int, optional): Count. Defaults to 3.
        *args: Extra.
        **kwargs (Any): More.

    Returns:
        bool: Whether it worked.
    """

def g_yield(n):
    """Count.

    Args:
        n (int): Limit.

    Yields:
        int: The next number.
    """
    yield from range(n)

def s_basic(path, size=None):
    """Sphinx.

    :param path: File.
    :type path: str or pathlib.Path
    :param int size: Size.
    :returns: Data.
    :rtype: bytes
    """

def s_dict(m):
    """
    :param m: Map.
    :type m: dict[str, int]
    :rtype: list[str]
    """

class Box:
    def area(self, scale):
        """Area.

        Args:
            scale (float): Factor.

        Returns:
            float: The area.
        """
