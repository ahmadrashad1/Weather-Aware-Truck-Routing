import threading
import time
from collections.abc import Callable

from config.observability import log_event

FAILURE_THRESHOLD = 3
OPEN_SECONDS = 30


class CircuitBreaker:
    """Stop calling a provider that keeps failing, so waiting on it can't tie up every thread.

    Three failures in a row pause calls for 30 seconds. After that, one call at a time is let
    through to test the provider, and a success ends the pause. A test call that never reports
    back only blocks others until the next pause ends.
    """

    def __init__(self, name: str, clock: Callable[[], float] = time.monotonic) -> None:
        self._name = name
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._retry_at = 0.0

    def allow(self) -> bool:
        with self._lock:
            if self._failures < FAILURE_THRESHOLD:
                return True
            now = self._clock()
            if now < self._retry_at:
                return False
            self._retry_at = now + OPEN_SECONDS
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures < FAILURE_THRESHOLD:
                return
            self._retry_at = self._clock() + OPEN_SECONDS
        log_event("circuit_opened", provider=self._name)


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(provider_name: str) -> CircuitBreaker:
    with _breakers_lock:
        return _breakers.setdefault(provider_name, CircuitBreaker(provider_name))


def reset_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()
