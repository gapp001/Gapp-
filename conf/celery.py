import json
import random
import time
from typing import Any, Dict, List
import requests
from celery import Celery
from stellar_sdk import Asset, Keypair, Server
from stellar_sdk.account import Account
from application.choices import StellarAccountStatus
from application.credentials import (get_credentials_from_redis,
                                     set_credentials_into_redis)
from application.repositories.django_repository import DjangoRepository
from application.repositories.stellar_repository import StellarRepository
from application.schemas import DjangoAuthCredentials, GAStellarAccountBoundedSchema, GAStellarAccountSchema
from redis import Redis
from conf.exceptions import NoIssuerAccountFound
from conf.redis import RDB, celery_blocker, task_blocker
from conf.settings import settings


app = Celery(__name__)
app.config_from_object(settings, namespace='CELERY')


# celery -A conf worker -l INFO


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        60.0 * settings.DJANGO_CREDENTIALS_TTL,
        configure_credentials_from_django.s(),
        name='Configure django credentials every 55 minutes'
    )
    sender.add_periodic_task(
        3.0,
        get_stellar_accounts_from_django_task.s(),
        name=f'Retrieving StellarAccount objects every 3 seconds'
    )
    sender.add_periodic_task(
        5.0,
        send_updated_stellar_accounts_to_django.s(),
        name=f'Sending `GAStellarAccountBoundedSchema` data to Django-server every 5 seconds'
    )
    # sender.add_periodic_task(
    #     60.0 * 60,
    #     send_transaction_result_to_django.s(),
    #     name=f'Send data to Django every 60 minutes'
    # )


@app.task(name='get_stellar_accounts_from_django_task')
@task_blocker(task_key='get_stellar_accounts_from_django_task', key_ttl=300)
def get_stellar_accounts_from_django_task(conn: Redis | None = None):
    """
        Function for retrieving `StellarAccount` objects
        with status `keypair_generated` from Django-server
    """
    timeout = 8.0
    conn = conn or RDB.get_redis_pool()
    with requests.Session() as session:
        credentials: DjangoAuthCredentials = get_credentials_from_redis(
            conn=conn, session=session, timeout=timeout)
            
        stellar_accounts: List[GAStellarAccountSchema] = DjangoRepository.get_stellar_accounts(
            session=session,
            timeout=timeout,
            access_token=credentials.access_token
        )

        server: Server = Server(settings.HORIZON_URL)
        issuer_keypair = Keypair.from_secret(
            secret=settings.ISSUER_SECRET_KEY)
        issuer_account: Account | None = StellarRepository.get_account(
            server=server,
            public_key=issuer_keypair.public_key,
        )

        if not issuer_account:
            raise NoIssuerAccountFound

        base_fee: int = server.fetch_base_fee()

        with conn.pipeline(transaction=True) as pipe:
            for account in stellar_accounts:
                # проверь kiss cache
                existing_account: Account | None = StellarRepository.get_account(
                    server=server,
                    public_key=account.public_key)
                if existing_account:
                    # Setting up GAStellarAccountBoundedSchema data to Redis
                    RDB.set_bounded_stellar_account(
                        pipe=pipe,
                        bounded_account=GAStellarAccountBoundedSchema(
                            pk=account.pk,
                            status=StellarAccountStatus.need_trustline.value,
                        ),
                    )
                    continue

                is_created_account: bool = StellarRepository.create_stellar_account(
                    server=server,
                    recipient_public_key=account.public_key,
                    issuer_keypair=issuer_keypair,
                    issuer_account=issuer_account,
                    base_fee=base_fee,
                )

                status: StellarAccountStatus = StellarAccountStatus.need_trustline if is_created_account \
                    else StellarAccountStatus.keypair_generated

                # Setting up GAStellarAccountBoundedSchema data to Redis
                RDB.set_bounded_stellar_account(
                    pipe=pipe,
                    bounded_account=GAStellarAccountBoundedSchema(
                        pk=account.pk, status=status.value),
                )
            pipe.execute()
            pipe.reset()


@app.task(name='send_updated_stellar_accounts_to_django')
@task_blocker(task_key='send_updated_stellar_accounts_to_django', key_ttl=300)
def send_updated_stellar_accounts_to_django(conn=None):
    """
        Function for sending `GAStellarAccountBoundedSchema` data to Django-server
    """
    timeout = 8.0
    conn = conn or RDB.get_redis_pool()
    with requests.Session() as session:
        credentials: DjangoAuthCredentials = get_credentials_from_redis(
            conn=conn, session=session, timeout=timeout)
        accounts: Dict[int, str] | None = RDB.get_bounded_stellar_accounts_data(
            conn=conn)
        request_data = [json.loads(account) for account in accounts.values()] if accounts else None
        if accounts:
            # Sending data to Django-server
            status_code = DjangoRepository.send_updated_stellar_accounts(
                session=session,
                timeout=timeout,
                access_token=credentials.access_token,
                data=request_data,
            )
            result: bool = status_code == 200
            if result:
                conn.hdel(RDB.STELLAR_ACCOUNTS_KEY, *accounts.keys())
            return result
        return False


# # @app.task(name='get_stellar_accounts_from_django_task')
# # @task_blocker(task_key='get_stellar_accounts_from_django_task')
# @app.task()
# def get_stellar_accounts_from_django_task():
#     """
#         Function for retrieving `StellarAccount` objects
#         with status `keypair_generated` from Django-server
#     """
#     # print('Started task get_stellar_accounts_from_django_task')
#     with celery_blocker(task_key='get_stellar_accounts_from_django_task') as blocker:
#         print(f'{blocker.can_start_task=}')
#         print(f'{blocker.conn=}')
#         if not blocker.can_start_task:
#             print('TASK IS LOCKED')
#             return
#         timeout = 8.0

#         with requests.Session() as session:
#             credentials: DjangoAuthCredentials = get_credentials_from_redis(conn=blocker.conn, session=session, timeout=timeout)
#             stellar_accounts = get_stellar_accounts_from_django(
#                 session=session,
#                 timeout=timeout,
#                 access_token=credentials.access_token
#             )
#             request_data: List[Dict[str, Any]] = []

#             for account in stellar_accounts:
#                 request_data.append(
#                     GAStellarAccountBoundedSchema(
#                         pk=account.pk,
#                         status=str(StellarAccountStatus.fulfilled.value),
#                     ).__dict__
#                 )
#                 print(f'Append Account with pk {account.pk}. Go to sleep 10 sec')
#                 time.sleep(10)

#                 # TODO implement here logic of creation stellar accounts

#             send_stellar_accounts_to_django(
#                 session=session,
#                 timeout=timeout,
#                 access_token=credentials.access_token,
#                 data=request_data,
#             )
#             # print(f'{stellar_accounts=}')
#     print('Finished task get_stellar_accounts_from_django_task\n')

    # time.sleep(10)


@ app.task(
    # name='configure_credentials_from_django',
    autoretry_for=(requests.HTTPError,),
    max_retries=53,
    default_retry_delay=60)
# @task_blocker(task_key='configure_credentials_from_django')
def configure_credentials_from_django(conn: Redis):
    timeout = 8.0
    with requests.Session() as session:
        access_token = conn.get('access_token')
        refresh_token = conn.get('refresh_token')
        if not access_token:
            credentials = DjangoRepository.get_credentials(
                session=session, timeout=timeout)
            set_credentials_into_redis(conn=conn, credentials=credentials)
            return {'success': True, 'updated': False}
        credentials = DjangoRepository.get_refreshed_credentials(
            session=session,
            timeout=timeout,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        set_credentials_into_redis(conn=conn, credentials=credentials)
        return {'success': True, 'updated': True}


@app.task()
def set_transaction_result_into_redis():
    conn = RDB.get_redis_pool()
    timeout = 8.0
    with requests.Session() as session:
        credentials = get_credentials_from_redis(
            conn=conn, session=session, timeout=timeout)
        transactions = DjangoRepository.get_transactions(
            session=session,
            timeout=timeout,
            access_token=credentials.access_token
        )
        # Подключились к серверу Stellar
        server = Server(horizon_url=settings.HORIZON_URL)
        # Fetch issuing keypair from secret key.
        # Получили пару ключей инициатора - Root Аккаунт
        issuing_keypair = Keypair.from_secret(
            secret=settings.ISSUER_SECRET_KEY)
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
                transaction_result = StellarRepository.send_transaction(
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


@app.task()
def send_transaction_result_to_django():
    conn = RDB.get_redis_pool()
    timeout = 8.0
    with requests.Session() as session:
        transactions = conn.hgetall('transactions')
        credentials = get_credentials_from_redis(
            conn=conn, session=session, timeout=timeout)
        response = session.post(
            url=f'{settings.DJANGO_DOMAIN}/stellar_microservice/transactions/',
            headers={'Authorization': f'Bearer {credentials.access_token}'},
            json=transactions,
        )
        response.raise_for_status()
        conn.hdel('transactions', *transactions.keys())
        return response.json()
