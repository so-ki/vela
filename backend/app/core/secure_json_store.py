"""Small-process safe persistence for auxiliary JSON state.

The production pilot intentionally runs one API worker. A process-wide reentrant
lock therefore serializes every read/modify/write sequence in that worker, while
same-directory temporary files plus ``os.replace`` prevent readers from seeing a
partially written file. These files are advisory state; formal review and audit
records remain transactional database data.
"""

from __future__ import annotations

import functools
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar

JSON_STORE_LOCK = threading.RLock()

P = ParamSpec("P")
R = TypeVar("R")


def synchronized_json_store(func: Callable[P, R]) -> Callable[P, R]:
    """Serialize a complete auxiliary-state operation within this process."""

    @functools.wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with JSON_STORE_LOCK:
            return func(*args, **kwargs)

    return wrapped


def _prepare_private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)


def _fsync_directory(path: Path) -> None:
    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        # Some filesystems do not support directory fsync. The file itself was
        # already fsynced and atomically replaced, so this is best-effort only.
        pass
    finally:
        os.close(directory_fd)


def atomic_write_bytes(path: Path | str, content: bytes) -> None:
    """Atomically replace ``path`` with mode 0600 and durable file contents."""

    destination = Path(path)
    with JSON_STORE_LOCK:
        _prepare_private_parent(destination)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            destination.chmod(0o600)
            _fsync_directory(destination.parent)
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise


def atomic_write_json(
    path: Path | str,
    payload: Any,
    *,
    sort_keys: bool = False,
) -> None:
    """Serialize JSON fully before atomically replacing the destination."""

    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=sort_keys,
        )
        + "\n"
    ).encode("utf-8")
    atomic_write_bytes(path, encoded)
