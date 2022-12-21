from contextlib import contextmanager
from dataclasses import dataclass
import json
from typing import Any, Callable, Dict, List, Optional
import redis
from application.choices import StellarAccountStatus
from application.schemas import GAStellarAccountBoundedSchema

from conf.settings import LOGGER, settings


class RDB:
    """Class helper for Redis"""
    RUNNING_TASK_VALUE: str = '1'
    STELLAR_ACCOUNTS_KEY: str = 'stellar_accounts'
    TRANSACTIONS_KEY: str = 'transactions'

    @staticmethod
    def get_redis_pool() -> redis.Redis:
        """Redis client bound to pool of connections (auto-reconnecting)"""
        return redis.Redis.from_url(url=settings.REDIS_HOST, encoding="utf-8", decode_responses=True)

    @staticmethod
    def set_bounded_stellar_account(pipe: redis.client.Pipeline, bounded_account: GAStellarAccountBoundedSchema, prefix: str = ''):
        """Method for setting up GAStellarAccountBoundedSchema data to Redis"""
        pipe.hset(
            f'{prefix}{__class__.STELLAR_ACCOUNTS_KEY}',
            bounded_account.pk,
            json.dumps(bounded_account.__dict__)
        )

    @staticmethod
    def delete_stellar_accounts(conn: redis.Redis, name: str, keys: List, prefix: str = ''):
        """Method for setting up GAStellarAccountBoundedSchema data to Redis"""
        conn.hdel(f'{prefix}{name}', *keys)

    @staticmethod
    def get_bounded_stellar_accounts_data(conn: redis.Redis, prefix: str = '') -> Dict[int, str] | None:
        """Method for retrieving GAStellarAccountBoundedSchema data from Redis"""
        return conn.hgetall(f'{prefix}{__class__.STELLAR_ACCOUNTS_KEY}')
         

    @staticmethod
    def get_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> int:
        """
            Method for returning task status from Redis
            If the value is 1, then the task is already running
        """
        _conn = conn or __class__.get_redis_pool()

        return _conn.get(task_key)

    @staticmethod
    def set_task_status(task_key: str, ttl: float = 120.0, conn: Optional[redis.Redis] = None) -> bool:
        """Method for setting up param with `task_key` to `RUNNING_TASK_VALUE` to Redis"""
        _conn = conn or __class__.get_redis_pool()
        return _conn.set(name=task_key, value=__class__.RUNNING_TASK_VALUE, ex=ttl)

    @staticmethod
    def remove_task_status(task_key: str, conn: Optional[redis.Redis] = None) -> bool:
        """Method for removing key with param `task_key` from  Redis"""
        _conn = conn or __class__.get_redis_pool()
        return _conn.delete(task_key)


def task_blocker(task_key: str, key_ttl: float = 120.0, can_ignore_lock: bool = False):
    """Decoration function for using blocking running celery task"""
    conn = RDB.get_redis_pool()

    def decorator(function: Callable):
        def wrapper(*args, **kwargs):
            task_status: str = RDB.get_task_status(
                task_key=task_key, conn=conn)
            can_start_task: bool = task_status != RDB.RUNNING_TASK_VALUE

            if can_ignore_lock:
                can_start_task = True

            if not can_start_task:
                LOGGER.debug('Task starting is blocked! Try later')

            else:
                # Setting to Redis that the celery task are running
                RDB.set_task_status(task_key=task_key, ttl=key_ttl, conn=conn)
            kwargs.update(conn=conn)
            try:
                if can_start_task:
                    # Running Celery task
                    # Blocking running task if prev task not completed
                    result: Any = function(*args, **kwargs)
                    return result
            except Exception as e:
                raise e
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
    conn = RDB.get_redis_pool()
    task_status: int = RDB.get_task_status(task_key=task_key, conn=conn)
    can_start_task: bool = task_status != RDB.RUNNING_TASK_VALUE
    LOGGER.debug(f'{task_status=}')
    try:
        if can_start_task:
            RDB.set_task_status(task_key=task_key, conn=conn)
        yield LockerDTO(
            can_start_task=can_start_task,
            conn=conn,
        )
    finally:
        LOGGER.debug(f'finally')
        if not can_start_task:
            LOGGER.debug(f'not can_start_task')
            RDB.remove_task_status(task_key=task_key, conn=conn)
        conn.close()
