"""A package whose modules all star-import each other resolves in linear time (shapely's layout)."""
from __future__ import annotations

import time

from stubpy import Config, generate


def test_star_import_web(tmp_path):
    pkg = tmp_path / "web"
    pkg.mkdir()
    n = 12
    (pkg / "__init__.py").write_text("".join(f"from .m{i} import *\n" for i in range(n)))
    for i in range(n):
        body = "".join(f"from .m{j} import *\n" for j in range(n) if j != i)
        if i == n - 1:
            body += "def target(x: int, *, scale: float = 1.0) -> None: ...\n"
        body += f"def f{i}(**kwargs):\n    return missing_{i}(**kwargs)\n"
        (pkg / f"m{i}.py").write_text(body)
    (pkg / "api.py").write_text("from . import *\n\ndef draw(**kwargs):\n    return target(**kwargs)\n")
    start = time.perf_counter()
    report = generate(pkg, tmp_path / "out", config=Config(imports="none"))
    assert report.ok
    assert time.perf_counter() - start < 30
    assert "scale: float = 1.0" in (tmp_path / "out" / "web" / "api.pyi").read_text()
