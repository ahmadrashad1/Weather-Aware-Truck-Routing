import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _survive_outage(on_failure: Callable[..., Any]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(method: Callable[P, R]) -> Callable[P, R]:
        @wraps(method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return method(*args, **kwargs)
            except (RedisError, OSError) as error:
                logger.warning("Redis is unavailable (%s)", type(error).__name__)
                return on_failure(*args, **kwargs)  # type: ignore[no-any-return]

        return wrapper

    return decorate


def _default_value(_cache: Any, _key: Any, default: Any = None, **_kwargs: Any) -> Any:
    return default


def _nothing_found(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}


def _nothing_done(*_args: Any, **_kwargs: Any) -> bool:
    return False


def _nothing_stored(_cache: Any, data: Any, *_args: Any, **_kwargs: Any) -> list[Any]:
    return list(data)


class ResilientRedisCache(RedisCache):
    """Treat a Redis outage as an empty cache.

    The cache only makes the app faster and protects provider quotas. Without this, losing Redis
    would fail every request, because throttling reads the cache before a view even runs.
    """

    get = _survive_outage(_default_value)(RedisCache.get)
    get_many = _survive_outage(_nothing_found)(RedisCache.get_many)
    set = _survive_outage(_nothing_done)(RedisCache.set)
    set_many = _survive_outage(_nothing_stored)(RedisCache.set_many)
    add = _survive_outage(_nothing_done)(RedisCache.add)
    delete = _survive_outage(_nothing_done)(RedisCache.delete)
