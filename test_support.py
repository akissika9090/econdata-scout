"""
Shared helper for the optional paper tests.

Some tests read real paper PDFs or saved extraction results. These materials are not distributed (copyright / size).
When any of them is missing, the test file stops before reading anything and reports SKIPPED with exit code 77,
listing exactly which files are missing. It does not catch errors from the tests themselves.
"""
import os

SKIP_CODE = 77


def require_materials(paths: list[str], suite: str) -> None:
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print(f"SKIPPED ({suite}): missing local materials (not distributed): " + ", ".join(missing))
        raise SystemExit(SKIP_CODE)
