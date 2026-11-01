from collections.abc import Iterator

import pytest
from django.core.cache import cache

from routing.providers.breaker import reset_breakers


@pytest.fixture(autouse=True)
def clear_cache() -> Iterator[None]:
    cache.clear()
    reset_breakers()
    yield
    cache.clear()
