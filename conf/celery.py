from decimal import Decimal
import json
from typing import Any, Dict, List
from sentry_sdk import capture_message, set_context
import requests
from celery import Celery
from stellar_sdk import Asset, Keypair, Server
from stellar_sdk.account import Account
from application.choices import StellarAccountStatus
from application.credentials import (get_credentials_from_redis,
                                     set_credentials_into_redis)
from application.repositories.django_repository import DjangoRepository, DjangoURLS
from application.repositories.stellar_repository import StellarRepository
from application.schemas import DjangoAuthCredentials, GAStellarAccountBoundedSchema, GAStellarAccountSchema, StellarPaymentTransactionSchema, StellarWallet
from redis import Redis
from conf.exceptions import NoIssuerAccountFound
from conf.redis import RDB, celery_blocker, task_blocker
from conf.settings import settings
from utils.gpg_helper import GPGHelper
from stellar_sdk.exceptions import (NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError, SignatureExistError)


app = Celery(__name__)
app.config_from_object(settings, namespace='CELERY')


# celery -A conf worker -l INFO


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        60.0 * settings.DJANGO_CREDENTIALS_TTL,
        configure_credentials_from_django_task.s(),
        name='Configure django credentials every 55 minutes'
    )
    sender.add_periodic_task(
        10.0,
        get_stellar_accounts_from_django_task.s(),
        name=f'Retrieving StellarAccount objects every 3 seconds'
    )
    sender.add_periodic_task(
        5.0,
        send_updated_stellar_accounts_to_django_task.s(),
        name=f'Sending `GAStellarAccountBoundedSchema` data to Django-server every 5 seconds'
    )
    sender.add_periodic_task(
        15.0,
        initial_accrual_stellar_accounts_task.s(),
        name=f'Accrual of the starting balance to the user every 5 seconds'
    )
    sender.add_periodic_task(
        8.0,
        send_transactions_to_stellar_task.s(),
        name=f'Send data to Stellar every 3 seconds'
    )
    sender.add_periodic_task(
        3.0,
        send_transaction_result_to_django_task.s(),
        name=f'Send Stellar transaction data to Django every 3 seconds'
    )


@app.task(name='initial_accrual_stellar_accounts_task')
@task_blocker(task_key='initial_accrual_stellar_accounts_task', key_ttl=300, )
def initial_accrual_stellar_accounts_task(conn: Redis | None = None):
    """
        Function for retrieving `StellarAccount` objects
        with status `fulfilled` from Django-server and initial accrual of funds
    """
    timeout = 8.0

    # This prefix used for Redis key
    PREFIX: str = 'accrual_funds'

    try:
        conn = conn or RDB.get_redis_pool()
        with requests.Session() as session:
            credentials: DjangoAuthCredentials = get_credentials_from_redis(
                conn=conn, session=session, timeout=timeout)

            stellar_accounts: List[GAStellarAccountSchema] = DjangoRepository.get_stellar_accounts_with_balances(
                session=session,
                timeout=timeout,
                access_token=credentials.access_token
            )

            if stellar_accounts:
                successful_deposit_accounts: List[GAStellarAccountBoundedSchema | None] = []

                server: Server = Server(settings.HORIZON_URL)
                issuer_keypair = Keypair.from_secret(
                    secret=settings.ISSUER_SECRET_KEY)
                issuer_account: Account | None = StellarRepository.get_account(
                    server=server,
                    public_key=issuer_keypair.public_key,
                )

                if not issuer_account:
                    raise NoIssuerAccountFound

                ga_ngn_asset: Asset = StellarRepository.get_asset(
                    issuer_public_key=issuer_keypair.public_key,
                    currency=settings.NGN_CURRENCY,
                )
                ga_usd_asset: Asset = StellarRepository.get_asset(
                    issuer_public_key=issuer_keypair.public_key,
                    currency=settings.USD_CURRENCY,
                )
                base_fee: int = server.fetch_base_fee()

                
                for account in stellar_accounts:
                    if account.ngn_balance == None or account.usd_balance == None:
                        not_founded_balance: str = 'ngn_balance' if not account.ngn_balance else 'usd_balance'

                        set_context(
                            'initial_accrual_stellar_accounts_task_case',
                            value=dict(public_key=account.public_key, )
                        )
                        capture_message(f'Django {not_founded_balance} is None (initial_accrual_stellar_accounts_task_case)', level='error')
                        continue

                    existing_account: Account | None = StellarRepository.get_account(
                        server=server,
                        public_key=account.public_key)

                    if not existing_account:
                        set_context(
                            'initial_accrual_stellar_accounts_task_case',
                            value=dict(public_key=account.public_key, )
                        )
                        capture_message(
                            'Stellar account not found (initial_accrual_stellar_accounts_task_case)', level='error')
                        continue

                    balances: Dict[str, StellarWallet] = StellarRepository.get_account_balances(raw_data=existing_account.raw_data)
                    ga_ngn_stellar_wallet: StellarWallet = balances.get(settings.GA_NGN_ASSET_CODE)
                    ga_usd_stellar_wallet: StellarWallet = balances.get(settings.GA_USD_ASSET_CODE)

                    if not ga_ngn_stellar_wallet:
                        set_context('initial_accrual_stellar_accounts_task_case',value=dict(public_key=account.public_key, ))
                        capture_message('GA_NGN Stellar wallet not found (initial_accrual_stellar_accounts_task_case)', level='error')
                        continue

                    if not ga_usd_stellar_wallet:
                        set_context('initial_accrual_stellar_accounts_task_case', value=dict(public_key=account.public_key, ))
                        capture_message('GA_USD Stellar wallet not found (initial_accrual_stellar_accounts_task_case)', level='error')
                        continue
                    
                    can_update_ga_ngn_wallet_balance: bool = StellarRepository.compare_balances(
                        stellar_wallet_balance=ga_ngn_stellar_wallet.balance,
                        ga_wallet_balance=account.ngn_balance,
                    )
                    
                    can_update_ga_usd_wallet_balance: bool = StellarRepository.compare_balances(
                        stellar_wallet_balance=ga_usd_stellar_wallet.balance,
                        ga_wallet_balance=account.usd_balance,
                    )
                    
                    if not can_update_ga_ngn_wallet_balance and not can_update_ga_usd_wallet_balance:
                        successful_deposit_accounts.append(GAStellarAccountBoundedSchema(pk=account.pk, is_initial_accrued_money=True))
                        continue

                    if can_update_ga_ngn_wallet_balance:
                        # Creating Stellar transaction with gaNGN asset
                        
                        ga_ngn_transaction_amount: Decimal = account.ngn_balance - ga_ngn_stellar_wallet.balance

                        try:
                            ga_ngn_transaction_result: StellarPaymentTransactionSchema = StellarRepository.send_transaction(
                                amount=ga_ngn_transaction_amount, recipient_public_key=account.public_key,
                                server=server, issuer_keypair=issuer_keypair,
                                issuer_account=issuer_account, base_fee=base_fee,
                                asset=ga_ngn_asset
                            )

                            is_ga_ngn_transaction_succeed: bool = StellarRepository.check_transaction_result(result_xdr=ga_ngn_transaction_result.result_xdr)

                        except (NotFoundError, BadRequestError, BadResponseError,
                                UnknownRequestError, ConnectionError, SignatureExistError,
                                AttributeError, ValueError) as e:
                            is_ga_ngn_transaction_succeed: bool = False

                        if not is_ga_ngn_transaction_succeed:
                            set_context('initial_accrual_stellar_accounts_task_case', value=transaction_result.dict())
                            capture_message('Stellar transaction not completed (initial_accrual_stellar_accounts_task_case)', level='error')
                            # continue

                        if is_ga_ngn_transaction_succeed and not can_update_ga_usd_wallet_balance:
                            # It means that this Django StellarAccount can set is_initial_accrued_money to True
                            successful_deposit_accounts.append(GAStellarAccountBoundedSchema(pk=account.pk, is_initial_accrued_money=True))
                   
                    if can_update_ga_usd_wallet_balance:
                        # Creating Stellar transaction with gaUSD asset

                        ga_usd_transaction_amount: Decimal = account.usd_balance - ga_usd_stellar_wallet.balance

                        try:
                            transaction_result: StellarPaymentTransactionSchema = StellarRepository.send_transaction(
                                amount=ga_usd_transaction_amount, recipient_public_key=account.public_key,
                                server=server, issuer_keypair=issuer_keypair,
                                issuer_account=issuer_account, base_fee=base_fee,
                                asset=ga_usd_asset
                            )

                            is_ga_usd_transaction_succeed: bool = StellarRepository.check_transaction_result(result_xdr=transaction_result.result_xdr)

                        except (NotFoundError, BadRequestError, BadResponseError,
                                UnknownRequestError, ConnectionError, SignatureExistError,
                                AttributeError, ValueError) as e:
                                is_ga_usd_transaction_succeed: bool = False

                        if not is_ga_usd_transaction_succeed:
                            set_context('initial_accrual_stellar_accounts_task_case', value=transaction_result.dict())
                            capture_message('Stellar transaction not completed (initial_accrual_stellar_accounts_task_case)', level='error')
                            # continue

                        if is_ga_usd_transaction_succeed:
                            # It means that this Django StellarAccount can set is_initial_accrued_money to True
                            successful_deposit_accounts.append(GAStellarAccountBoundedSchema(pk=account.pk, is_initial_accrued_money=True))

                # if there is data, send them to the Django server
                if successful_deposit_accounts:
                    request_data: List[Dict[str, Any]] = [_account.dict() for _account in successful_deposit_accounts]
                    status_code = DjangoRepository.send_updated_stellar_accounts(
                        session=session, timeout=timeout,
                        access_token=credentials.access_token,
                        data=request_data, url=DjangoURLS.POST_SEND_UPDATED_BALANCES_STELLAR_ACCOUNTS
                    )
   
        print(f'DONE initial_accrual_stellar_accounts_task\n')
    except Exception as e:
        set_context('initial_accrual_stellar_accounts_task_case',
                    value=e.__dict__)
        capture_message(
            'Error in initial_accrual_stellar_accounts_task', level='error')
        raise e


@app.task(name='get_stellar_accounts_from_django_task')
@task_blocker(task_key='get_stellar_accounts_from_django_task', key_ttl=300, )
def get_stellar_accounts_from_django_task(conn: Redis | None = None):
    """
        Function for retrieving `StellarAccount` objects
        with status `keypair_generated` from Django-server
    """
    timeout = 8.0
    try:
        conn = conn or RDB.get_redis_pool()
        with requests.Session() as session:
            credentials: DjangoAuthCredentials = get_credentials_from_redis(
                conn=conn, session=session, timeout=timeout)

            stellar_accounts: List[GAStellarAccountSchema] = DjangoRepository.get_stellar_accounts(
                session=session,
                timeout=timeout,
                access_token=credentials.access_token
            )
            print(f'\nget_stellar_accounts_from_django_task')
            print(f'{stellar_accounts=}')
            if stellar_accounts:
                server: Server = Server(settings.HORIZON_URL)
                issuer_keypair = Keypair.from_secret(
                    secret=settings.ISSUER_SECRET_KEY)
                issuer_account: Account | None = StellarRepository.get_account(
                    server=server,
                    public_key=issuer_keypair.public_key,
                )

                if not issuer_account:
                    raise NoIssuerAccountFound

                ga_ngn_asset: Asset = StellarRepository.get_asset(
                    issuer_public_key=issuer_keypair.public_key,
                    currency=settings.NGN_CURRENCY,
                )
                ga_usd_asset: Asset = StellarRepository.get_asset(
                    issuer_public_key=issuer_keypair.public_key,
                    currency=settings.USD_CURRENCY,
                )
                base_fee: int = server.fetch_base_fee()

                with conn.pipeline(transaction=True) as pipe:
                    for account in stellar_accounts:
                        can_skip_create_operation: bool = False

                        # проверь kiss cache
                        existing_account: Account | None = StellarRepository.get_account(
                            server=server,
                            public_key=account.public_key)
                        if existing_account:
                            account_wallets: List[Dict[str, Any]] = existing_account.raw_data.get(
                                'balances')
                            has_trustline: bool = StellarRepository.check_trustline_exists(
                                account_wallets)
                            # Setting up GAStellarAccountBoundedSchema data to Redis
                            if has_trustline:
                                RDB.set_bounded_stellar_account(
                                    pipe=pipe,
                                    bounded_account=GAStellarAccountBoundedSchema(
                                        pk=account.pk,
                                        status=StellarAccountStatus.fulfilled.value,
                                    ),
                                )
                                continue
                            else:
                                can_skip_create_operation = True

                        if not account.private_key:
                            set_context('get_stellar_accounts_from_django_task_case', value=dict(account=account.__dict__))
                            capture_message('Error in get_stellar_accounts_from_django_task (account.private_key is None)', level='error')
                            continue
                        # Decrypting Stellar secret key
                        decrypted_private_key: bytes = GPGHelper.root_key_helper.decrypt_message(
                            message=account.private_key).data

                        if isinstance(decrypted_private_key, bytes):
                            decrypted_private_key: str = decrypted_private_key.decode()

                        if not can_skip_create_operation:
                            is_created_account: bool = StellarRepository.create_stellar_account(
                                server=server,
                                recipient_public_key=account.public_key,
                                issuer_keypair=issuer_keypair,
                                issuer_account=issuer_account,
                                base_fee=base_fee,
                            )
                        else:
                            is_created_account = True

                        if is_created_account:
                            # Create trustline between issuer and receiver
                            recipient_keypair = Keypair.from_secret(
                                decrypted_private_key)
                            has_created_trustline: bool = StellarRepository.change_trust_operation(
                                server=server,
                                recipient_keypair=recipient_keypair,
                                base_fee=base_fee,
                                ga_ngn_asset=ga_ngn_asset,
                                ga_usd_asset=ga_usd_asset,
                            )

                            if has_created_trustline:
                                # Setting up GAStellarAccountBoundedSchema data to Redis
                                status: StellarAccountStatus = StellarAccountStatus.fulfilled if has_created_trustline \
                                    else StellarAccountStatus.keypair_generated
                                RDB.set_bounded_stellar_account(
                                    pipe=pipe,
                                    bounded_account=GAStellarAccountBoundedSchema(
                                        pk=account.pk,
                                        status=status.value,
                                        private_key=account.private_key if status != StellarAccountStatus.fulfilled else None
                                    ),
                                )

                    pipe.execute()
                    pipe.reset()
        print(f'DONE get_stellar_accounts_from_django_task\n')
    except Exception as e:
        set_context('get_stellar_accounts_from_django_task_case',
                    value=e.__dict__)
        capture_message(
            'Error in get_stellar_accounts_from_django_task', level='error')
        raise e


@app.task(name='send_updated_stellar_accounts_to_django')
@task_blocker(task_key='send_updated_stellar_accounts_to_django', key_ttl=300, )
def send_updated_stellar_accounts_to_django_task(conn=None):
    """
        Function for sending `GAStellarAccountBoundedSchema` data to Django-server
    """
    print('\nsend_updated_stellar_accounts_to_django_task')
    timeout = 8.0
    try:
        conn = conn or RDB.get_redis_pool()
        with requests.Session() as session:
            credentials: DjangoAuthCredentials = get_credentials_from_redis(
                conn=conn, session=session, timeout=timeout)
            accounts: Dict[int, str] | None = RDB.get_bounded_stellar_accounts_data(
                conn=conn)
            request_data = [json.loads(
                account) for account in accounts.values()] if accounts else None
            if accounts:
                # Sending data to Django-server
                print(f'UPDATED STELLAR ACCOUNTS: {accounts=}')
                status_code = DjangoRepository.send_updated_stellar_accounts(
                    session=session,
                    timeout=timeout,
                    access_token=credentials.access_token,
                    data=request_data,
                    url=DjangoURLS.POST_SEND_UPDATED_STELLAR_ACCOUNTS_STATUS
                )
                result: bool = status_code == 200
                if result:
                    RDB.delete_stellar_accounts(conn=conn, name=RDB.STELLAR_ACCOUNTS_KEY, keys=accounts.keys())
                    # conn.hdel(RDB.STELLAR_ACCOUNTS_KEY, *accounts.keys())
                print('DONE send_updated_stellar_accounts_to_django_task DONE')
                return result
            print('DONE send_updated_stellar_accounts_to_django_task DONE')
            return False
    except Exception as e:
        set_context('send_updated_stellar_accounts_to_django_task',
                    value=e.__dict__)
        capture_message(
            'Error in send_updated_stellar_accounts_to_django_task', level='error')
        raise e

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


@app.task(
    # name='configure_credentials_from_django',
    autoretry_for=(requests.HTTPError,),
    max_retries=53,
    default_retry_delay=60)
# @task_blocker(task_key='configure_credentials_from_django')
def configure_credentials_from_django_task(conn: Redis):
    timeout = 8.0
    try:
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
    except Exception as e:
        set_context('configure_credentials_from_django_task', value=e.__dict__)
        capture_message(
            'Error in configure_credentials_from_django_task', level='error')
        raise e


@app.task(name='send_stellar_transactions_task')
@task_blocker(task_key='send_stellar_transactions_task', key_ttl=300, )
def send_transactions_to_stellar_task(conn=None):
    print('send_transactions_to_stellar_task')
    try:
        conn = conn or RDB.get_redis_pool()
        timeout = 8.0
        with requests.Session() as session:
            credentials = get_credentials_from_redis(
                conn=conn, session=session, timeout=timeout)
            transactions = DjangoRepository.get_transactions(
                session=session,
                timeout=timeout,
                access_token=credentials.access_token
            )
            if transactions:
                # Подключились к серверу Stellar
                server = Server(horizon_url=settings.HORIZON_URL)
                # Fetch issuing keypair from secret key.
                # Получили пару ключей инициатора - Root Аккаунт
                issuer_keypair = Keypair.from_secret(
                    secret=settings.ISSUER_SECRET_KEY)
                # Fetch the current sequence number for the source account from Horizon.
                # Получаем по публичному ключу данные аккаунта
                issuer_account = server.load_account(issuer_keypair.public_key)

                # Fetch the current base fee for the transaction
                # Получаем минимальную комиисию за транзакцию
                base_fee = server.fetch_base_fee()

                # Create an object to represent the new asset
                # Получаем валюту GA coin TODO разберись

                with conn.pipeline(transaction=True) as pipe:
                    for ga_transaction in transactions:
                        stellar_transaction_is_exists: bool = conn.hget(
                            RDB.TRANSACTIONS_KEY, ga_transaction.id)
                        if stellar_transaction_is_exists:
                            continue

                        asset: Asset = StellarRepository.get_asset(
                            issuer_public_key=issuer_keypair.public_key, currency=ga_transaction.amount_currency)
                        recipient_public_key: str = ga_transaction.related_user.stellar_account.public_key
                        try:
                            transaction_result: StellarPaymentTransactionSchema = StellarRepository.send_transaction(
                                ga_transaction_id=ga_transaction.id,
                                amount=ga_transaction.amount,
                                recipient_public_key=recipient_public_key,
                                server=server,
                                issuer_keypair=issuer_keypair,
                                issuer_account=issuer_account,
                                base_fee=base_fee,
                                asset=asset
                            )
                        except Exception as e:
                            # here not catched exception to Sentry because it's catched in StellarRepository.send_transaction
                            transaction_result = None
                        print(f'{transaction_result=}')
                        if transaction_result:
                            pipe.hset(
                                RDB.TRANSACTIONS_KEY,
                                ga_transaction.id,
                                transaction_result.json()
                            )
                    pipe.execute()
                    pipe.reset()
            print('DONE send_transactions_to_stellar_task')
        return {'success': True}
    except Exception as e:
        set_context('send_transactions_to_stellar_task', value=e.__dict__)
        capture_message(
            'Error in send_transactions_to_stellar_task', level='error')
        raise e


@app.task(name='send_transaction_result_to_django_task')
@task_blocker(task_key='send_transaction_result_to_django_task', key_ttl=300)
def send_transaction_result_to_django_task(conn=None):
    print('send_transaction_result_to_django_task')
    try:
        conn = conn or RDB.get_redis_pool()
        timeout = 8.0
        with requests.Session() as session:
            transactions = conn.hgetall('transactions')
            print(f'{transactions=}')
            if transactions:
                credentials = get_credentials_from_redis(
                    conn=conn, session=session, timeout=timeout)
                response = session.post(
                    url=f'{settings.DJANGO_DOMAIN}{DjangoURLS.POST_SEND_STELLAR_WEBHOOK}',
                    headers={
                        'Authorization': f'Bearer {credentials.access_token}'},
                    json=[json.loads(transaction)
                          for transaction in transactions.values()],
                )
                response.raise_for_status()
                conn.hdel('transactions', *transactions.keys())
                print('DONE send_transaction_result_to_django_task')
                return response.status_code == 200
    except Exception as e:
        set_context('send_transaction_result_to_django_task', value=e.__dict__)
        capture_message('Error in send_transaction_result_to_django_task', level='error')
        raise e
