from __future__ import annotations

from functools import lru_cache

import redis

from app.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
