from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Optional
import redis

from conf.settings import settings


class RDB:
    """Class helper for Redis"""
    RUNNING_TASK_VALUE: str = '1'

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
        # return __class__.atomic_get(key=task_key, conn=conn)

        return _conn.get(task_key)

    @staticmethod
    def set_task_status(task_key: str, ttl: float = 120.0, conn: Optional[redis.Redis] = None) -> bool:
        """Method for setting up param with `task_key` to `RUNNING_TASK_VALUE` to Redis"""
        _conn = conn or __class__.get_redis_pool_for_celery_task()
        return _conn.set(name=task_key, value=__class__.RUNNING_TASK_VALUE, ex=ttl)

    @staticmethod
    def remove_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> bool:
        """Method for removing key with param `task_key` from  Redis"""
        _conn = conn or __class__.get_redis_pool_for_celery_task()
        return _conn.delete(task_key)

    @staticmethod
    def atomic_get(key: str, conn: redis.Redis):
        with conn.pipeline() as pipe:
            try:
                # put a WATCH on the key that holds our sequence value
                pipe.watch(key)
                # after WATCHing, the pipeline is put into immediate execution
                # mode until we tell it to start buffering commands again.
                # this allows us to get the current value of our sequence
                if pipe.exists(key):
                    return pipe.get(key)
                # now we can put the pipeline back into buffered mode with MULTI
                pipe.multi()
                # pipe.set(some_key, F())
                # pipe.get(some_key)
                # and finally, execute the pipeline (the set and get commands)
                return pipe.execute()
                # if a WatchError wasn't raised during execution, everything
                # we just did happened atomically.
            except redis.WatchError:
                # another client must have changed some_key between
                # the time we started WATCHing it and the pipeline's execution.
                # Let's just get the value they changed it to.
                return pipe.get(key)

def task_blocker(task_key: str, ttl: float = 120.0):
    """Decoration function for using blocking running celery task"""
    conn = RDB.get_redis_pool_for_celery_task()
    def do_nothing():...

    def decorator(function: Callable):
        def wrapper(*args, **kwargs):
            task_status: str = RDB.get_task_status(task_key=task_key, conn=conn)
            can_start_task: bool = task_status != RDB.RUNNING_TASK_VALUE
            print(f'{can_start_task=}')
            if not can_start_task:
                print('Task starting is blocked! Try later')
            
            else:
                # Setting to Redis that the celery task are running
                RDB.set_task_status(task_key=task_key, ttl=ttl, conn=conn)
            # Running Celery task
            kwargs.update(conn=conn)
            try:
                # Blocking running task if prev task not completed
                result: Any = function(*args, **kwargs) if can_start_task else do_nothing()
                return result
            finally:
                if can_start_task:
                    # Removing task key from Redis
                    RDB.remove_task_status(task_key=task_key, conn=conn)
                
        return wrapper
    try:
        return decorator
    finally:
        conn.close()

@dataclass
class LockerDTO:
    can_start_task: bool
    conn: redis.Redis

@contextmanager
def celery_blocker(task_key: str):
    conn = RDB.get_redis_pool_for_celery_task()
    task_status: int = RDB.get_task_status(task_key=task_key, conn=conn)
    can_start_task: bool = task_status != RDB.RUNNING_TASK_VALUE
    print(f'{task_status=}') 
    try:
        if can_start_task:
            RDB.set_task_status(task_key=task_key, conn=conn)
        yield LockerDTO(
            can_start_task=can_start_task,
            conn=conn,
        )
    finally:
        print(f'finally')
        if not can_start_task:
            print(f'not can_start_task')
            RDB.remove_task_status(task_key=task_key, conn=conn)
        conn.close()

def task_blocker_manager(task_key: str):
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