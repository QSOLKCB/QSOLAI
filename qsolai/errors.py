"""Stable QSOLAI error types and machine-readable codes."""

from __future__ import annotations


class QSOLAIError(Exception):
    """A controlled failure with a stable code and process exit status."""

    def __init__(self, code: str, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def fail(code: str, message: str, exit_code: int = 2) -> "None":
    raise QSOLAIError(code, message, exit_code)
