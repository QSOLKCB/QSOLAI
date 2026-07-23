#!/usr/bin/env python3
"""Verify that the QSOLAI runtime contains no direct network client."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "qsolai"
FORBIDDEN = {"socket", "urllib", "http", "httpx", "requests", "aiohttp", "ftplib", "smtplib", "websocket", "websockets"}


def main() -> None:
    failures: list[str] = []
    for path in sorted(RUNTIME.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                names = []
            for name in names:
                if name in FORBIDDEN:
                    failures.append(f"network import {name}: {path.name}:{node.lineno}")
    if failures:
        raise SystemExit("NETWORK_AUDIT_FAILED\n" + "\n".join(sorted(failures)))
    print("PASS no direct network client imports in qsolai runtime; default authority remains SIM_ONLY")


if __name__ == "__main__":
    main()
