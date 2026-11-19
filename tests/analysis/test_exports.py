"""
Tests for the cached source harvest in stubpy.analysis.exports.
"""
from __future__ import annotations

import os

from stubpy.analysis.exports import harvest_file


def test_rewrite_with_same_mtime_is_reharvested(tmp_path):
    file = tmp_path / "m.py"
    file.write_text("class A: ...\n")
    stamp = os.stat(file).st_mtime_ns
    assert [c.name for c in harvest_file(file).classes] == ["A"]
    file.write_text("class B: ...\n")
    os.utime(file, ns=(stamp, stamp))
    assert [c.name for c in harvest_file(file).classes] == ["B"]
