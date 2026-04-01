#!/usr/bin/env python3
"""
tests/run_all_tests.py
----------------------
Runs the full test suite without requiring pytest to be installed.
Discovers every class starting with ``Test`` and every method starting
with ``test_`` in the specified test modules, executes them, and reports
results in the same style as the baseline runner.

Usage (from project root):
    PYTHONPATH=. python3 tests/run_all_tests.py
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

# Ensure project root is on the path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MODULES = [
    "tests.test_module_symbols",
    "tests.test_special_classes",
]

passed = failed = 0
_errors: list[tuple[str, str]] = []


def run_test(label: str, fn) -> None:
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✓ {label}")
    except Exception:
        failed += 1
        _errors.append((label, traceback.format_exc()))
        last_line = traceback.format_exc().strip().splitlines()[-1]
        print(f"  ✗ {label}: {last_line}")


def run_module(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    short = module_name.split(".")[-1]
    print(f"\n── {short} ──────────────────────────────────────────────────────────")
    for cls_name in dir(mod):
        if not cls_name.startswith("Test"):
            continue
        cls = getattr(mod, cls_name)
        if not isinstance(cls, type):
            continue
        print(f"  [{cls_name}]")
        instance = cls()
        # Run setup_method equivalent if present
        for method_name in dir(cls):
            if not method_name.startswith("test_"):
                continue
            method = getattr(instance, method_name)
            if callable(method):
                run_test(f"{cls_name}.{method_name}", method)


if __name__ == "__main__":
    for mod_name in TEST_MODULES:
        try:
            run_module(mod_name)
        except Exception:
            print(f"\n  ERROR importing {mod_name}:")
            traceback.print_exc()
            failed += 1

    total = passed + failed
    print()
    print("═" * 65)
    print(f"  TOTAL: {total}  |  ✓ {passed} passed  |  ✗ {failed} failed")
    print("═" * 65)

    if _errors:
        print("\nFailed tests detail:")
        for name, tb in _errors:
            print(f"\n  FAILED: {name}")
            for line in tb.strip().splitlines()[-6:]:
                print(f"    {line}")
        sys.exit(1)
    else:
        print("\n  All tests passed ✓")
