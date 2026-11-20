import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


class RateLimiter:
    """Fixed-window counter in Redis. Fails OPEN: if Redis is down, logins still work."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Count one attempt. Returns (allowed, seconds_until_the_window_resets)."""
        try:
            pipe = self.client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if ttl is None or ttl < 0:  # first hit, or an expiry that was never set
                self.client.expire(key, window_seconds)
                ttl = window_seconds
            return count <= limit, max(int(ttl), 1)
        except Exception:  # noqa: BLE001
            logger.warning("Rate limiter unavailable; allowing the request", exc_info=True)
            return True, 0

    def reset(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("Could not reset rate limit key", exc_info=True)


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    import redis

    from api.core.config import app_config

    return RateLimiter(redis.Redis.from_url(app_config.REDIS_URL, socket_timeout=1, socket_connect_timeout=1))