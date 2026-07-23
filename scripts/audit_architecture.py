#!/usr/bin/env python3
"""Static architecture audit for the constrained Python kernel."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "qsolai"
FORBIDDEN_SUFFIXES = {".html", ".css", ".js", ".mjs", ".jsx", ".ts", ".tsx", ".wasm"}
FORBIDDEN_NAMES = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
FORBIDDEN_CALLS = {"eval", "exec"}
FORBIDDEN_ENTROPY_IMPORTS = {"random", "secrets", "uuid"}


def imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def main() -> None:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or "dist" in path.parts or "runs" in path.parts:
            continue
        if path.is_file() and (path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name in FORBIDDEN_NAMES):
            failures.append(f"forbidden frontend/build artifact: {path.relative_to(ROOT)}")
    for path in sorted(RUNTIME.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for root in imported_roots(tree):
            if root != "qsolai" and root not in sys.stdlib_module_names:
                failures.append(f"third-party runtime import {root}: {path.name}")
            if root in FORBIDDEN_ENTROPY_IMPORTS:
                failures.append(f"hidden entropy import {root}: {path.name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                failures.append(f"dynamic code execution {node.func.id}: {path.name}:{node.lineno}")
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        failures.append(f"shell=True: {path.name}:{node.lineno}")
        if "import pickle" in source or "from pickle" in source:
            failures.append(f"pickle import: {path.name}")
        if "os.urandom" in source:
            failures.append(f"hidden entropy call os.urandom: {path.name}")
    if failures:
        raise SystemExit("ARCHITECTURE_AUDIT_FAILED\n" + "\n".join(sorted(failures)))
    print("PASS standard-library Python kernel; no frontend, dynamic execution, pickle, shell=True, or third-party runtime imports")


if __name__ == "__main__":
    main()
