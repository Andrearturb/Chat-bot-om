"""Serialize manual and scheduled Tape imports in the API process."""
from contextlib import contextmanager
from threading import Lock

_lock = Lock()


class TapeSyncBusyError(RuntimeError):
    pass


@contextmanager
def tape_sync_guard():
    if not _lock.acquire(blocking=False):
        raise TapeSyncBusyError('Uma sincronização da Tape já está em andamento.')
    try:
        yield
    finally:
        _lock.release()
