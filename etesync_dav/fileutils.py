"""Safe helpers for files containing credentials."""

import os
import stat
import tempfile
from contextlib import contextmanager

from filelock import FileLock

_locks = {}


def _lock_for(path):
    normalized = os.path.normcase(os.path.abspath(path))
    return _locks.setdefault(normalized, FileLock(f"{normalized}.lock"))


@contextmanager
def locked_path(path):
    """Serialize access to a path across threads and processes."""
    with _lock_for(path):
        yield


def atomic_write_text(path, content):
    """Atomically replace *path* with private, flushed UTF-8 content."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".etesync-dav-", dir=directory, text=True)
    try:
        os.chmod(temporary_path, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def open_log_file(path, fallback_directory):
    """Open a log path without letting an invalid path prevent startup."""
    if not path:
        return None

    candidates = (path, os.path.join(fallback_directory, "etesync-dav.log"))
    for candidate in dict.fromkeys(candidates):
        try:
            directory = os.path.dirname(os.path.abspath(candidate))
            os.makedirs(directory, mode=0o700, exist_ok=True)
            output = open(candidate, "a", encoding="utf-8")
            os.chmod(candidate, stat.S_IRUSR | stat.S_IWUSR)
            return output
        except OSError:
            continue
    return None
