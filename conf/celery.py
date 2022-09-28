import time
import requests
from celery import Celery
from stellar_sdk import Asset, Keypair, Server

from application.credentials import (get_credentials_from_django,
                                     get_credentials_from_redis,
                                     get_refreshed_credentials_from_django,
                                     set_credentials_into_redis)
from application.schemas import DjangoAuthCredentials
from application.utils import (get_stellar_accounts_from_django, get_transactions_from_django,
                               send_transaction_to_stellar)
from redis import Redis
from conf.redis import RDB, task_blocker
from conf.settings import settings


app = Celery(__name__)
app.config_from_object(settings, namespace='CELERY')


# celery -A conf worker -l INFO


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        60.0 * 55,
        configure_credentials_from_django.s(),
        name='Configure django credentials every 55 minutes'
    )
    sender.add_periodic_task(
        1.0,
        get_stellar_accounts_from_django_task.s(),
        name=f'Retrieving StellarAccount objects every 1 seconds'
    )
    # sender.add_periodic_task(
    #     60.0 * 60,
    #     send_transaction_result_to_django.s(),
    #     name=f'Send data to Django every 60 minutes'
    # )


    
@app.task(name='get_stellar_accounts_from_django_task')
@task_blocker(task_key='get_stellar_accounts_from_django_task')
def get_stellar_accounts_from_django_task(conn: Redis):
    """
        Function for retrieving `StellarAccount` objects 
        with status `keypair_generated` from Django-server
    """
    print('Started task get_stellar_accounts_from_django_task')
    timeout = 8.0
    
    with requests.Session() as session:
        credentials: DjangoAuthCredentials = get_credentials_from_redis(conn=conn, session=session, timeout=timeout)
        stellar_accounts = get_stellar_accounts_from_django(
            session=session,
            timeout=timeout,
            access_token=credentials.access_token
        )
        print(f'{stellar_accounts=}')
    print('Finished task get_stellar_accounts_from_django_task\n')
    time.sleep(10)


@app.task(
    name='configure_credentials_from_django',
    autoretry_for=(requests.HTTPError,),
    max_retries=53,
    default_retry_delay=60)
@task_blocker(task_key='configure_credentials_from_django')
def configure_credentials_from_django(conn: Redis):
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


# @app.task()
def set_transaction_result_into_redis():
    conn = RDB.get_redis_pool_for_celery_task()
    timeout = 8.0
    with requests.Session() as session:
        credentials = get_credentials_from_redis(conn=conn, session=session, timeout=timeout)
        transactions = get_transactions_from_django(
            session=session,
            timeout=timeout,
            access_token=credentials.access_token
        )
        # Подключились к серверу Stellar
        server = Server(horizon_url=settings.HORIZON_URL)
        # Fetch issuing keypair from secret key.
        # Получили пару ключей инициатора - Root Аккаунт
        issuing_keypair = Keypair.from_secret(secret=settings.ISSUER_SECRET_KEY)
        # Fetch the current sequence number for the source account from Horizon.
        # Получаем по публичному ключу данные аккаунта
        issuer = server.load_account(issuing_keypair.public_key)

        # Fetch the current base fee for the transaction
        # Получаем минимальную комиисию за транзакцию
        base_fee = server.fetch_base_fee()

        # Create an object to represent the new asset
        # Получаем валюту GA coin TODO разберись
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


# @app.task()
def send_transaction_result_to_django():
    conn = RDB.get_redis_pool_for_celery_task()
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
