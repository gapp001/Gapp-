from typing import Any, Callable, Optional
import redis

from conf.settings import settings


class RDB:
    """Class helper for Redis"""
    RUNNING_TASK_VALUE: int = 1

    @staticmethod
    def get_redis_pool_for_celery_task() -> redis.Redis:
        """Redis client bound to pool of connections (auto-reconnecting)"""
        return redis.Redis.from_url(url=settings.REDIS_HOST, encoding="utf-8", decode_responses=True)

    @staticmethod
    def get_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> int:
        """
            Method for returning task status from Redis
            If the value is 1, then the task is already running
        """
        _conn = conn or __class__.get_redis_pool_for_celery_task()
        return _conn.get(task_key)

    @staticmethod
    def set_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> bool:
        """Method for setting up param with `task_key` to `RUNNING_TASK_VALUE` to Redis"""
        _conn = conn or __class__.get_redis_pool_for_celery_task()
        return _conn.set(name=task_key, value=__class__.RUNNING_TASK_VALUE)

    @staticmethod
    def remove_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> bool:
        """Method for removing key with param `task_key` from  Redis"""
        _conn = conn or __class__.get_redis_pool_for_celery_task()
        return _conn.delete(task_key)


def task_blocker(task_key: str):
    """Decoration function for using blocking running celery task"""
    conn = RDB.get_redis_pool_for_celery_task()
    can_start_task: bool = RDB.get_task_status(task_key=task_key, conn=conn) != RDB.RUNNING_TASK_VALUE
    if not can_start_task:
        # Blocking running task if prev task not completed
        print('Task starting is blocked! Try later')
        return
    def decorator(function: Callable):
        def wrapper(*args, **kwargs):
            # Setting to Redis that the celery task are running
            RDB.set_task_status(task_key=task_key, conn=conn)
            
            # Running Celery task
            kwargs.update(conn=conn)
            try:
                result: Any = function(*args, **kwargs)
                return result
            finally:
                # Removing task key from Redis
                RDB.remove_task_status(task_key=task_key, conn=conn)
                
        return wrapper
    try:
        return decorator
    finally:
        conn.close()