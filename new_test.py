from decimal import Decimal
import random
import requests
from redis import Redis
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from stellar_sdk.xdr.transaction_result import TransactionResult
from stellar_sdk.xdr.payment_result_code import PaymentResultCode
from stellar_sdk.asset import Asset
from stellar_sdk.keypair import Keypair
from stellar_sdk.network import Network
from stellar_sdk.server import Server
from stellar_sdk.account import Account
from stellar_sdk.exceptions import NotFoundError
from application.repositories.stellar_repository import StellarRepository
from application.schemas import StellarPaymentTransactionSchema, TransactionResultSchema
from conf.celery import get_stellar_accounts_from_django_task, send_transaction_result_to_django_task, send_updated_stellar_accounts_to_django_task, send_transactions_to_stellar_task
from conf.redis import RDB
from conf.settings import settings


@dataclass
class ConstantsDTO:
    TESTNET: str = 'https://horizon-testnet.stellar.org'
    # Root issuer keypair
    ROOT_ISSUER_SECRET_KEY: str = 'SCVGEUZ4RSJL5BPTP6CZFYQJTDECUX767HNWWIENZKZFSCCVLHHJ3VHO'
    DEFAULT_TIMEOUT: int = 31536000  # One year in seconds

    # Recipient's keypair
    RECIPIENT_1_PUBLIC_KEY: str = 'GCAFT4KTT5CG72E57ATGYLQFVDXNBGYNKNS7XYI73ZPSOLGOGJIA4R4R'
    RECIPIENT_1_SECRET_KEY: str = 'SDZAFQQDWGKUNSAFOCCODFHGKAG6A6HHKCTRY2L3RACDR2RY4B54K6FQ'
    RECIPIENT_2_PUBLIC_KEY: str = 'GD435GSIGYGYBA2YC5TFM3IAUSILSUDEICBGQBSJHFCA4SFMRPWYATMY'
    RECIPIENT_2_SECRET_KEY: str = 'SDYU5RMG665JGLS5KPEM3D4DFWWKL4SBVICPIQHXGYPO66H2REXCOAP5'
    RECIPIENT_3_PUBLIC_KEY: str = 'GDD3EWF7BS74TKN25K7MNO4LDFFXH63VP7AQVV7P3NSGYH476GEOZYP6'
    RECIPIENT_3_SECRET_KEY: str = 'SB5JFJSEHL43JSZUI4QGXVDUIAFKPIBSGIUYDWOD3WXAWPJUTAEKYMFJ'

    GA_NGNG_ASSET_CODE: str = 'gaNGN'


def get_issuer_account(server: Server) -> Account:
    issuer_keypair: Keypair = Keypair.from_secret(
        ConstantsDTO.ROOT_ISSUER_SECRET_KEY)
    try:
        return server.load_account(issuer_keypair.public_key)
    except NotFoundError:
        print('Issuer Account not found. Creating account...')
        is_root_account_created: bool = create_root_account(
            public_key=issuer_keypair.public_key)
        if is_root_account_created:
            return server.load_account(issuer_keypair.public_key)
        raise Exception('Creation account error')


def create_root_account(public_key: Optional[str] = None) -> bool:
    url = 'https://friendbot.stellar.org'
    _response = requests.get(url, params={'addr': public_key})
    return _response.get('success')


def get_or_create_stellar_account(server: Server, recipient_public_key: str, issuer_account: Account, issuer_keypair: Keypair, base_fee: int) -> Account:
    try:
        account: Account = server.load_account(recipient_public_key)
        # print('Account was created earlier')
        return account
    except NotFoundError:
        is_recipient_account_created: Dict[str, Any] = StellarRepository.create_stellar_account(
            server=server,
            recipient_public_key=recipient_public_key,
            issuer_keypair=issuer_keypair,
            issuer_account=issuer_account,
            base_fee=base_fee,
        )
        if is_recipient_account_created:
            print('Account has created now')
            return server.load_account(recipient_public_key)
        raise Exception('Creation account error')


def set_transactions_to_redis():
    transactions = [TransactionResultSchema(
        transaction_id=i,
        public_key=random.randint(11111111, 99999999),
        stellar_transaction_hash='abcde' * random.randint(1, 5),
        stellar_transaction_status=1,
        stellar_transaction_detail='success'
    ) for i in range(5)]
    conn: Redis = RDB.get_redis_pool()
    with conn.pipeline(transaction=True) as pipe:
        for transaction in transactions:

            pipe.hset(
                'transactions',
                transaction.transaction_id,
                transaction.json()
            )
        pipe.execute()
        pipe.reset()

    transactions = conn.hgetall('transactions')

    print(f'{transactions.values()=}')


def create_trustline(server: Server,
                     recipient_keypair: Keypair,
                     base_fee: int,
                     ga_ngn_asset: Asset,
                     ga_usd_asset: Asset,):
    return StellarRepository.change_trust_operation(
        server=server,
        recipient_keypair=recipient_keypair,
        base_fee=base_fee,
        ga_ngn_asset=ga_ngn_asset,
        ga_usd_asset=ga_usd_asset,
    )


def check_transaction_result(result_xdr: str) -> bool:
    transaction_result = TransactionResult.from_xdr(result_xdr)
    try:
        transaction = transaction_result.result.results[0]
        return transaction.tr.payment_result.code == PaymentResultCode.PAYMENT_SUCCESS
    except IndexError:
        return False


if __name__ == "__main__":
    # get_stellar_accounts_from_django_task()
    # send_updated_stellar_accounts_to_django()

    server = Server(horizon_url=ConstantsDTO.TESTNET)

    base_fee: int = server.fetch_base_fee()
    issuer_keypair: Keypair = Keypair.from_secret(
        ConstantsDTO.ROOT_ISSUER_SECRET_KEY)
    issuer_account = get_issuer_account(server=server)
    # asset = Asset(
    #     code=ConstantsDTO.GA_NGNG_ASSET_CODE,
    #     issuer=issuer_keypair.public_key
    # )

    ga_ngn_asset: Asset = StellarRepository.get_asset(
        issuer_public_key=issuer_keypair.public_key,
        currency=settings.NGN_CURRENCY,
    )
    ga_usd_asset: Asset = StellarRepository.get_asset(
        issuer_public_key=issuer_keypair.public_key,
        currency=settings.USD_CURRENCY,
    )

    # # Recipient Account #1 ↓
    # account_1: Account = get_or_create_stellar_account(
    #     server=server,
    #     recipient_public_key=ConstantsDTO.RECIPIENT_1_PUBLIC_KEY,
    #     issuer_keypair=issuer_keypair,
    #     issuer_account=issuer_account,
    # )

    # ae92833e4f4ebe26737bcb2cbb94aa6e4fa89982e2933dcfa903bd6c8e836aa5 # transacfion between acc_1 and acc_2

    # account_1_balances: List[Dict[str, Any]
    #                          ] = account_1.raw_data.get('balances')
    # print('Account 1 Balances')

    # for balance in account_1_balances:

    #     print(f'_____\n{balance}\nimage.png_____\n')

    # Recipient Account #1 ↑
    # account_1_keypair = Keypair.from_secret(
    #     ConstantsDTO.RECIPIENT_1_SECRET_KEY)

    # print(account_1.__dict__)

    # # Recipient Account #2 ↓
    # account_2: Account = get_or_create_stellar_account(
    #     server=server,
    #     recipient_public_key=ConstantsDTO.RECIPIENT_2_PUBLIC_KEY,
    #     issuer_keypair=issuer_keypair,
    #     issuer_account=issuer_account,
    # )

    # print('\nAccount 2 Balances')
    # account_2_balances: List[Dict[str, Any]
    #                          ] = account_2.raw_data.get('balances')
    # for balance in account_2_balances:

    #     print(f'_____\n{balance}\n_____\n')
    # Recipient Account #2 ↑
    # print()
    # print(created_trustline)
    # print()
    # print(account_1.__dict__)
    # print()
    # print()
    # account_2_keypair = Keypair.from_secret(
    #     ConstantsDTO.RECIPIENT_2_SECRET_KEY)

  # Recipient Account #3 ↓
    # account_3: Account = get_or_create_stellar_account(
    #     server=server,
    #     base_fee=base_fee,
    #     recipient_public_key=ConstantsDTO.RECIPIENT_3_PUBLIC_KEY,
    #     issuer_keypair=issuer_keypair,
    #     issuer_account=issuer_account,
    # )

    # account_3_keypair = Keypair.from_secret(
    #     ConstantsDTO.RECIPIENT_3_SECRET_KEY)

    # created_trustline = create_trustline(
    #     server=server,
    #     recipient_keypair=account_3_keypair,
    #     base_fee=base_fee,
    #     ga_ngn_asset=ga_ngn_asset,
    #     ga_usd_asset=ga_usd_asset,
    # )

    # print(f'{create_trustline=}')
    # get_stellar_accounts_from_django_task()
    # send_updated_stellar_accounts_to_django_task()
    send_transactions_to_stellar_task()
    send_transaction_result_to_django_task()
    # payment_operation: StellarPaymentTransactionSchema =  StellarRepository.send_transaction(
    #     amount=Decimal('555.55'),
    #     recipient_public_key=account_2_keypair.public_key,
    #     issuer_account=account_1,
    #     issuer_keypair=account_1_keypair,
    #     server=server,
    #     base_fee=base_fee,
    #     asset=asset,
    # )

    # payment_operation: StellarPaymentTransactionSchema =  StellarRepository.send_transaction(
    #     amount=Decimal('500.00'),
    #     recipient_public_key=account_1_keypair.public_key,
    #     issuer_account=issuer_account,
    #     issuer_keypair=issuer_keypair,
    #     server=server,
    #     base_fee=base_fee,
    #     asset=asset,
    # )

    # print(payment_operation)

    # set_transactions_to_redis()
    # get_stellar_accounts_from_django_task()
    # send_updated_stellar_accounts_to_django()

"""
    payment transaction dict

{
    'id': '58244dbebf462bc74caaa6c50b670d36463ae8e3b9ce812003b1553bb1559951',
    'paging_token': '1417493826514944',
    'successful': True,
    'hash': '58244dbebf462bc74caaa6c50b670d36463ae8e3b9ce812003b1553bb1559951',
    'ledger': 330036,
    'created_at': datetime.datetime(2022, 10, 4, 11, 15, 56, tzinfo = datetime.timezone.utc),
    'source_account': 'GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L',
    'source_account_sequence': '1337104923623429',
    'fee_account': 'GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L',
    'fee_charged': '100',
    'max_fee': '100',
    'operation_count': 1,
    'envelope_xdr': 'AAAAAgAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAAGQABMAXAAAABQAAAAEAAAAAAAAAAAAAAABlHUliAAAAAAAAAAEAAAAAAAAAAQAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAJnYU5HTgAAAAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAABKgXyAAAAAAAAAAABxf+0wwAAAEBFGiPT+uoWqjyxSp1QW6+rwcHBXBKJicxUopCABFPmAvafbVxF5wQ7KTukBz57Sf6Z68YyGI8r5ZV+IPZgs6MI',
    'result_xdr': 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAABAAAAAAAAAAA=',
    'result_meta_xdr': 'AAAAAgAAAAIAAAADAAUJNAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAAXP/iFbAAEwBcAAAAEAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABQkYAAAAAGM8FVkAAAAAAAAAAQAFCTQAAAAAAAAAAPk5wUTYxGLn6yYoV9CYutBKNM9G03R8xGvWXVjF/7TDAAAAFz/4hWwABMAXAAAABQAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAMAAAAAAAUJNAAAAABjPBXsAAAAAAAAAAEAAAACAAAAAwAFCTIAAAABAAAAAIBZ8VOfRG/onfgmbC4FqO7Qmw1TZfvhH95fJyzOMlAOAAAAAmdhTkdOAAAAAAAAAAAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAAAAAAAAAf/////////8AAAABAAAAAAAAAAAAAAABAAUJNAAAAAEAAAAAgFnxU59Eb+id+CZsLgWo7tCbDVNl++Ef3l8nLM4yUA4AAAACZ2FOR04AAAAAAAAAAAAAAPk5wUTYxGLn6yYoV9CYutBKNM9G03R8xGvWXVjF/7TDAAAAASoF8gB//////////wAAAAEAAAAAAAAAAAAAAAA=',
    'fee_meta_xdr': 'AAAAAgAAAAMABQkYAAAAAAAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAABc/+IXQAATAFwAAAAQAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAAAAAAAAAAAAAAAAADAAAAAAAFCRgAAAAAYzwVWQAAAAAAAAABAAUJNAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAAXP/iFbAAEwBcAAAAEAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABQkYAAAAAGM8FVkAAAAA',
    'memo_type': 'none',
    'signatures': ['RRoj0/rqFqo8sUqdUFuvq8HBwVwSiYnMVKKQgART5gL2n21cRecEOyk7pAc+e0n+mevGMhiPK+WVfiD2YLOjCA=='],
    'valid_after': datetime.datetime(1970, 1, 1, 0, 0, tzinfo = datetime.timezone.utc),
    'valid_before': datetime.datetime(2023, 10, 4, 11, 15,
        46, tzinfo = datetime.timezone.utc)
}

"""

"""
'_links': {
    'self': {
        'href': 'https://horizon-testnet.stellar.org/transactions/9cef5b3fe0e6e340e5a4168384b4441469d1140abd8510238fa762995a326cfd'
    },
    'account': {
        'href': 'https://horizon-testnet.stellar.org/accounts/GCAFT4KTT5CG72E57ATGYLQFVDXNBGYNKNS7XYI73ZPSOLGOGJIA4R4R'
    },
    'ledger': {
        'href': 'https://horizon-testnet.stellar.org/ledgers/329297'
    },
    'operations': {
        'href': 'https://horizon-tesnYU5HTgAAAAAAAAAAAAAATkVAFkZ0whZQeyR89viSMJvXSIwArdaVkmexh1eYgvB//////////wAAAAAAAAABzjJQDgAAAEBhtneIDF8UxM1cW3e7GVvo+zB1tAGwS9wbDNwdJFq/KqnWYIThnfJy21ffects': {
                'href': 'https://horizon-testnet.sKmJRKBdRAkxJMmGY8fA1e0b0qnm1wP',
                'result_xdr': 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAGAAAAAAAAAAA=',
                'result_meta_xdr': 'AAAAAgAAAAIAAAADAAUGUQAAAAAAAAAAgFnx {'
                href ': '
                https: //horizon-testnet.stellar.oU59Eb+id+CZsLgWo7tCbDVNl++Ef3l8nLM4yUA4AAAAAB00zPAAEwGgAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAABAAUGUQAAAAAAAAAAgFnxU59Eb+id+CZsLgWo7tCbDVN5675008'}, 'transaction': {'href': 'https://l++Ef3l8nLM4yUA4AAAAAB00zPAAEwGgAAAABAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABQZRAAAAAGM8BrwAAAAAAAd1140abd8510238fa762995a326cfd', 'paging_tokAAAQAAAAMAAAAAAAUGUQAAAAEAAAAAgFnxU59Eb+id+CZsLgWo7tCbDVNl++Ef3l8nLM4yUA4AAAACZ2FOR04AAAAAAAAAAAAAAE5FQBZGdMIWUHskfPb4kjCb10iMAK3WlZJnsYdXmILwAAAAAAAAA: '2022-10-04T10:11:08Z', 'source_account': AB//////////wAAAAEAAAAAAAAAAAAAAAMABQZRAAAAAAAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAAHTTM8AATAaAAAAAEAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAABBGYNKNS7XYI73ZPSOLGOGJIA4R4R', 'fee_charged'AAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAAAAAAAAAAAAAAAAADAAAAAAAFBlEAAAAAYzwGvAAAAAAAAAABAAUGUQAAAAAAAAAAgFnxU59Eb+id+CZsLgWo7tCbDVNl++Ef3l8nLM4yUA4AAAAAB00zPAAAAAAABlHTo1AAAAAAAAAAEAAAAAAAAABgAAAAJnYU5HTEwGgAAAABAAAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABQZRAAAAAGM8BrwAAAAAAAAAAA==', 'fee_meta_xdr': 'AAdRAkxJMmGY8fA1e0b0qnm1wP', 'result_xdr': 'AAAAAgAAAAMABMBoAAAAAAAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAAHTTOgAATAaAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAEABQZRAAAAAAAAAAEwGgAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAAHTTM8AATAaAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAA==', 'memo_type': 'none', 'signatures': ['AAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABQZRAAAAAYbZ3iAxfFMTNXFt3uxlb6PswdbQBsEvcGwzcHSRavyqp1mCE4Z3ycttSpiUSgXUQJMSTJhmPHwNXtG9Kp5tcDw=='], 'valid_after': '1970-01-01T00:00:00Z', 'valid_before': '202mILwAAAAAAAAAAB//////////wAAAAEAAAAAAAAAAAAA3-10-04T10:11:01Z', 'preconditions': {'timebounds': {'min_time': '0', 'max_time': '1696414261'}}}
"""


"""
StellarRepository.create_stellar_account response
{
    '_links': {
        'self': {
            'href': 'https://horizon-testnet.stellar.org/transactions/23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8'
        },
        'account': {
            'href': 'https://horizon-testnet.stellar.org/accounts/GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L'
        },
        'ledger': {
            'href': 'https://horizon-testnet.stellar.org/ledgers/311400'
        },
        'operations': {
            'href': 'https://horizon-testnet.stellar.org/transactions/23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8/operations{?cursor,limit,order}',
            'templated': True
        },
        'effects': {
            'href': 'https://horizon-testnet.stellar.org/transactions/23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8/effects{?cursor,limit,order}',
            'templated': True
        },
        'precedes': {
            'href': 'https://horizon-testnet.stellar.org/transactions?order=asc&cursor=1337452815978496'
        },
        'succeeds': {
            'href': 'https://horizon-testnet.stellar.org/transactions?order=desc&cursor=1337452815978496'
        },
        'transaction': {
            'href': 'https://horizon-testnet.stellar.org/transactions/23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8'
        }
    },
    'id': '23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8',
    'paging_token': '1337452815978496',
    'successful': True,
    'hash': '23be1ee41c7307779a85c240bb7b5ecf42016bd4739e16b300ac2339843331c8',
    'ledger': 311400,
    'created_at': '2022-10-03T08:04:03Z',
    'source_account': 'GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L',
    'source_account_sequence': '1337104923623425',
    'fee_account': 'GD4TTQKE3DCGFZ7LEYUFPUEYXLIEUNGPI3JXI7GENPLF2WGF762MGX3L',
    'fee_charged': '100',
    'max_fee': '100',
    'operation_count': 1,
    'envelope_xdr': 'AAAAAgAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAAGQABMAXAAAAAQAAAAEAAAAAAAAAAAAAAABlG8quAAAAAAAAAAEAAAAAAAAAAAAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAAHTTOgAAAAAAAAAAHF/7TDAAAAQF8pK0nmD7UGTlWdYrPw9IEw3GG+XXs05uQtHOp6LSzgurywrf16UnP6EMcvrduX5Q9mZVcNZD3y/wRGYmwNXAc=',
    'result_xdr': 'AAAAAAAAAGQAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAA=',
    'result_meta_xdr': 'AAAAAgAAAAIAAAADAATAaAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAAXSHbnnAAEwBcAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAABAATAaAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAAXSHbnnAAEwBcAAAABAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABMBoAAAAAGM6l3MAAAAAAAAAAQAAAAMAAAADAATAaAAAAAAAAAAA+TnBRNjEYufrJihX0Ji60Eo0z0bTdHzEa9ZdWMX/tMMAAAAXSHbnnAAEwBcAAAABAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAwAAAAAABMBoAAAAAGM6l3MAAAAAAAAAAQAEwGgAAAAAAAAAAPk5wUTYxGLn6yYoV9CYutBKNM9G03R8xGvWXVjF/7TDAAAAF0Eps/wABMAXAAAAAQAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAMAAAAAAATAaAAAAABjOpdzAAAAAAAAAAAABMBoAAAAAAAAAACAWfFTn0Rv6J34JmwuBaju0JsNU2X74R/eXycszjJQDgAAAAAHTTOgAATAaAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAA=',
    'fee_meta_xdr': 'AAAAAgAAAAMABMAXAAAAAAAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAABdIdugAAATAFwAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAEABMBoAAAAAAAAAAD5OcFE2MRi5+smKFfQmLrQSjTPRtN0fMRr1l1Yxf+0wwAAABdIduecAATAFwAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAA==',
    'memo_type': 'none',
    'signatures': ['XykrSeYPtQZOVZ1is/D0gTDcYb5dezTm5C0c6notLOC6vLCt/XpSc/oQxy+t25flD2ZlVw1kPfL/BEZibA1cBw=='],
    'valid_after': '1970-01-01T00:00:00Z',
    'valid_before': '2023-10-03T08:02:54Z',
    'preconditions': {
        'timebounds': {
            'min_time': '0',
            'max_time': '1696320174'
        }
    }
}


"""
