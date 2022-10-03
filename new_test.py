import random
import requests
from redis import Redis
from dataclasses import dataclass
from typing import Any, Dict, Optional
from stellar_sdk.asset import Asset
from stellar_sdk.keypair import Keypair
from stellar_sdk.network import Network
from stellar_sdk.server import Server
from stellar_sdk.account import Account
from stellar_sdk.exceptions import NotFoundError
from application.repositories.stellar_repository import StellarRepository
from application.schemas import TransactionResultSchema
from conf.celery import get_stellar_accounts_from_django_task, send_updated_stellar_accounts_to_django
from conf.redis import RDB


@dataclass
class ConstantsDTO:
    TESTNET: str = 'https://horizon-testnet.stellar.org'
    # Root issuer keypair
    ROOT_ISSUER_SECRET_KEY: str = 'SCVGEUZ4RSJL5BPTP6CZFYQJTDECUX767HNWWIENZKZFSCCVLHHJ3VHO'
    DEFAULT_TIMEOUT: int = 31536000  # One year in seconds

    # Recipient's keypair
    RECIPIENT_PUBLIC_KEY: str = 'GCAFT4KTT5CG72E57ATGYLQFVDXNBGYNKNS7XYI73ZPSOLGOGJIA4R4R'
    RECIPIENT_SECRET_KEY: str = 'SDZAFQQDWGKUNSAFOCCODFHGKAG6A6HHKCTRY2L3RACDR2RY4B54K6FQ'

    GA_NGNG_ASSET_CODE: str = 'gaNGN'


def create_root_account(public_key: Optional[str] = None) -> bool:
    url = 'https://friendbot.stellar.org'
    _response = requests.get(url, params={'addr': public_key})
    return _response.get('success')


def create_stellar_account_case():
    server = Server(horizon_url=ConstantsDTO.TESTNET)
    base_fee: int = server.fetch_base_fee()

    issuer_keypair: Keypair = Keypair.from_secret(
        ConstantsDTO.ROOT_ISSUER_SECRET_KEY)
    try:
        issuer_account: Account = server.load_account(
            issuer_keypair.public_key)
    except NotFoundError:
        print('Issuer Account not found. Creating account...')
        is_root_account_created: bool = create_root_account(
            public_key=issuer_keypair.public_key)
    try:
        recipient_account: Account = server.load_account(
            ConstantsDTO.RECIPIENT_PUBLIC_KEY)
    except NotFoundError:
        is_recipient_account_created: Dict[str, Any] = StellarRepository.create_stellar_account(
            server=server,
            recipient_public_key=ConstantsDTO.RECIPIENT_PUBLIC_KEY,
            issuer_keypair=issuer_keypair,
            issuer_account=issuer_account,
            base_fee=base_fee,
        )
    print(f'{is_recipient_account_created=}')


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


if __name__ == "__main__":
    # create_stellar_account_case()
    # set_transactions_to_redis()
    get_stellar_accounts_from_django_task()
    send_updated_stellar_accounts_to_django()

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
