import threading
from collections.abc import Iterator
from contextlib import contextmanager


class ServerBusy(Exception):
    """Every slot for heavy work is taken."""


class HeavyRequestLimiter:
    """Refuse heavy work when full, so searches and health checks still get a thread.

    A queue would only hold threads for longer, and trips can already take over a minute.
    """

    def __init__(self, limit: int) -> None:
        self._slots = threading.BoundedSemaphore(limit) if limit else None

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._slots or not self._slots.acquire(blocking=False):
            raise ServerBusy
        try:
            yield
        finally:
            self._slots.release()
