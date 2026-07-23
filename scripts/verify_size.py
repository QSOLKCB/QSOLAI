#!/usr/bin/env python3
"""Fail when the runnable QSOLAI core exceeds its internal floppy budget."""

from __future__ import annotations

import sys
from pathlib import Path


LIMIT = 1_350_000


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("USAGE: verify_size.py ARTIFACT")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit("SIZE_ARTIFACT_MISSING")
    size = path.stat().st_size
    if size > LIMIT:
        raise SystemExit(f"SIZE_LIMIT_EXCEEDED {size} > {LIMIT}")
    print(f"PASS {size} <= {LIMIT}; remaining {LIMIT - size}")


if __name__ == "__main__":
    main()
