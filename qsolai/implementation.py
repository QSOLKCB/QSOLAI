"""Identity of the exact source bundle defining QSOLAI runtime semantics."""

from __future__ import annotations

from importlib import resources
import re
from typing import Any

from .canonical import DOMAINS, MAX_SAFE_INTEGER, domain_hash, sha256_bytes, without_self_hash
from .errors import QSOLAIError


ENGINE_VERSION = "0.1.0"
IMPLEMENTATION_MODULES = (
    "adapters.py",
    "adjudication.py",
    "archive.py",
    "artifacts.py",
    "canonical.py",
    "cli.py",
    "contracts.py",
    "engine.py",
    "errors.py",
    "implementation.py",
    "planner.py",
    "prompting.py",
    "state.py",
    "verification.py",
)


def _normalized_source(name: str) -> bytes:
    raw = resources.files("qsolai").joinpath(name).read_bytes()
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def build_implementation_identity() -> dict[str, object]:
    files = []
    for name in IMPLEMENTATION_MODULES:
        body = _normalized_source(name)
        files.append({"path": f"qsolai/{name}", "byte_length": len(body), "sha256": sha256_bytes(body)})
    core: dict[str, object] = {
        "schema": "qsolai.implementation/v1",
        "engine_version": ENGINE_VERSION,
        "source_normalization": "UTF-8 text; CRLF and CR normalized to LF",
        "source_files": files,
    }
    return {**core, "source_bundle_sha256": domain_hash(DOMAINS["implementation"], core)}


def validate_implementation_identity(value: Any) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"schema", "engine_version", "source_normalization", "source_files", "source_bundle_sha256"}:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation record keys are invalid")
    if value["schema"] != "qsolai.implementation/v1" or value["engine_version"] != ENGINE_VERSION:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation schema or engine version is invalid")
    if value["source_normalization"] != "UTF-8 text; CRLF and CR normalized to LF":
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source normalization is invalid")
    if type(value["source_files"]) is not list or not value["source_files"]:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source files are invalid")
    paths: list[str] = []
    for row in value["source_files"]:
        if type(row) is not dict or set(row) != {"path", "byte_length", "sha256"}:
            raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source row is invalid")
        if type(row["path"]) is not str or not row["path"]:
            raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source path is invalid")
        if type(row["byte_length"]) is not int or not 0 <= row["byte_length"] <= MAX_SAFE_INTEGER:
            raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source length is invalid")
        if type(row["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
            raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source hash is invalid")
        paths.append(row["path"])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation source paths are not canonical")
    source_hash = value["source_bundle_sha256"]
    if type(source_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation bundle hash is invalid")
    if domain_hash(DOMAINS["implementation"], without_self_hash(value, "source_bundle_sha256")) != source_hash:
        raise QSOLAIError("IMPLEMENTATION_IDENTITY_INVALID", "implementation bundle hash mismatch")
    return value
