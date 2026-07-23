"""Deterministic ZIP_STORED run archives."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .canonical import sha256_bytes
from .errors import QSOLAIError


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_FILE_MODE = 0o100644 << 16


def deterministic_zip_bytes(run_dir: Path) -> bytes:
    root = run_dir.resolve()
    if not root.is_dir() or root.is_symlink():
        raise QSOLAIError("ARCHIVE_RUN_INVALID", "archive source must be a safe run directory")
    paths = sorted(path for path in root.rglob("*") if path.is_file())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.comment = b""
        for path in paths:
            if path.is_symlink():
                raise QSOLAIError("ARCHIVE_SYMLINK_FORBIDDEN", "archive cannot contain symbolic links")
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = FIXED_FILE_MODE
            info.extra = b""
            info.comment = b""
            info.flag_bits = 0x800
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def pack_run(run_dir: Path, output: Path | None = None) -> dict[str, object]:
    body = deterministic_zip_bytes(run_dir)
    target = output or run_dir.with_name(run_dir.name + ".qsolai.zip")
    source_root = run_dir.resolve()
    resolved_target = target.resolve()
    if resolved_target == source_root or source_root in resolved_target.parents:
        raise QSOLAIError("ARCHIVE_OUTPUT_UNSAFE", "archive output must be outside the run directory")
    if target.exists():
        raise QSOLAIError("ARCHIVE_OUTPUT_EXISTS", "archive output already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(body)
    return {"status": "PASS", "path": str(target), "byte_length": len(body), "sha256": sha256_bytes(body)}
