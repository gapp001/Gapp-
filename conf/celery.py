import requests
from celery import Celery
from stellar_sdk import Asset, Keypair, Server

from application.credentials import (get_credentials_from_django,
                                     get_credentials_from_redis,
                                     get_refreshed_credentials_from_django,
                                     set_credentials_into_redis)
from application.utils import (get_transactions_from_django,
                               send_transaction_to_stellar)
from conf.redis import get_redis_pool_for_celery_task
from conf.settings import settings


celery = Celery(__name__)
celery.config_from_object(settings, namespace='CELERY')

# celery -A conf worker -l INFO


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        60.0 * 55,
        configure_credentials_from_django.s(),
        name='Configure django credentials every 55 minutes'
    )
    sender.add_periodic_task(
        60.0 * 60,
        send_transaction_result_to_django.s(),
        name=f'Send data to Django every 60 minutes'
    )


@celery.task(autoretry_for=(requests.HTTPError,), max_retries=53, default_retry_delay=60)
def configure_credentials_from_django():
    conn = get_redis_pool_for_celery_task()
    timeout = 8.0
    with requests.Session() as session:
        access_token = conn.get('access_token')
        refresh_token = conn.get('refresh_token')
        if not access_token:
            credentials = get_credentials_from_django(session=session, timeout=timeout)
            set_credentials_into_redis(conn=conn, credentials=credentials)
            return {'success': True, 'updated': False}
        credentials = get_refreshed_credentials_from_django(
            session=session,
            timeout=timeout,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        set_credentials_into_redis(conn=conn, credentials=credentials)
        return {'success': True, 'updated': True}


@celery.task()
def set_transaction_result_into_redis():
    conn = get_redis_pool_for_celery_task()
    timeout = 8.0
    with requests.Session() as session:
        credentials = get_credentials_from_redis(conn=conn, session=session, timeout=timeout)
        transactions = get_transactions_from_django(
            session=session,
            timeout=timeout,
            access_token=credentials.access_token
        )

        server = Server(horizon_url=settings.HORIZON_URL)
        # Fetch issuing keypair from secret key.
        issuing_keypair = Keypair.from_secret(secret=settings.ISSUER_SECRET_KEY)
        # Fetch the current sequence number for the source account from Horizon.
        issuer = server.load_account(issuing_keypair.public_key)
        # Fetch the current base fee for the transaction
        base_fee = server.fetch_base_fee()
        # Create an object to represent the new asset
        asset = Asset(settings.ASSET_CODE, issuing_keypair.public_key)
        with conn.pipeline(transaction=True) as pipe:
            for transaction in transactions:
                transaction_result = send_transaction_to_stellar(
                    transaction=transaction,
                    server=server,
                    issuing_keypair=issuing_keypair,
                    issuer=issuer,
                    base_fee=base_fee,
                    asset=asset
                )
                pipe.hset(
                    'transactions',
                    transaction_result.transaction_id,
                    transaction_result.json()
                )
            pipe.execute()
            pipe.reset()

    return {'success': True}


@celery.task()
def send_transaction_result_to_django():
    conn = get_redis_pool_for_celery_task()
    timeout = 8.0
    with requests.Session() as session:
        transactions = conn.hgetall('transactions')
        credentials = get_credentials_from_redis(conn=conn, session=session, timeout=timeout)
        response = session.post(
            url=f'{settings.DJANGO_DOMAIN}/stellar_microservice/transactions/',
            headers={'Authorization': f'Bearer {credentials.access_token}'},
            json=transactions,
        )
        response.raise_for_status()
        conn.hdel('transactions', *transactions.keys())
        return response.json()
