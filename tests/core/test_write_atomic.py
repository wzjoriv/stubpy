"""
Tests for the line endings stubpy writes.
"""
from __future__ import annotations

import os

from stubpy.core._output import write_atomic


def test_new_file_is_written_with_lf(tmp_path):
    target = tmp_path / "m.pyi"
    write_atomic(target, "x: int\ny: str\n")
    assert target.read_bytes() == b"x: int\ny: str\n"


def test_existing_crlf_file_keeps_crlf(tmp_path):
    target = tmp_path / "m.pyi"
    target.write_bytes(b"old: int\r\n")
    write_atomic(target, "x: int\n")
    assert target.read_bytes() == b"x: int\r\n"


def test_existing_lf_file_keeps_lf(tmp_path):
    target = tmp_path / "m.pyi"
    target.write_bytes(b"old: int\n")
    write_atomic(target, "x: int\n")
    assert target.read_bytes() == b"x: int\n"


def test_raw_writes_text_unchanged(tmp_path):
    target = tmp_path / "m.pyi"
    write_atomic(target, "a\r\nb\n", raw=True)
    assert target.read_bytes() == b"a\r\nb\n"


def test_unchanged_file_is_not_rewritten(tmp_path):
    target = tmp_path / "m.pyi"
    write_atomic(target, "x: int\n")
    stamp = target.stat().st_mtime_ns
    os.utime(target, ns=(stamp - 10**9, stamp - 10**9))
    write_atomic(target, "x: int\n")
    assert target.stat().st_mtime_ns == stamp - 10**9


def test_changed_crlf_file_is_rewritten_with_crlf(tmp_path):
    target = tmp_path / "m.pyi"
    target.write_bytes(b"x: int\r\n")
    write_atomic(target, "x: int\n")
    assert target.read_bytes() == b"x: int\r\n"
    write_atomic(target, "y: str\n")
    assert target.read_bytes() == b"y: str\r\n"
