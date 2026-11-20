"""
Tests for the line endings stubpy writes.
"""
from __future__ import annotations

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
