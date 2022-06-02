import redis

from conf.settings import settings


def get_redis_pool_for_celery_task():
    # Redis client bound to pool of connections (auto-reconnecting).
    return redis.Redis.from_url(url=settings.REDIS_HOST, encoding="utf-8", decode_responses=True)
