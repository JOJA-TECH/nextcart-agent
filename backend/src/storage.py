"""Utilidades de persistencia: JSON atómico, JSONL, hash y tiempo."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json_atomic(path: Path | str, obj: Any, *, indent: int | None = 2) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    text = json.dumps(obj, ensure_ascii=False, indent=indent, allow_nan=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def append_jsonl(path: Path | str, obj: Any) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def sha256_of_file(path: Path | str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def log_step(message: str) -> None:
    print(f"[{now_utc_iso()}] {message}", flush=True)


class StepTimer:
    """Context manager que informa duración de un paso en consola."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __enter__(self) -> "StepTimer":
        self._t0 = datetime.now(timezone.utc)
        log_step(f"INICIO: {self.label}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = (datetime.now(timezone.utc) - self._t0).total_seconds()
        if exc_type is None:
            log_step(f"FIN: {self.label} ({elapsed:.1f}s)")
        else:
            log_step(f"ERROR: {self.label} ({elapsed:.1f}s) -> {exc}")
