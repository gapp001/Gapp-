from decimal import Decimal
import sys
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from stellar_sdk import Asset, Keypair, Account, Network, Server, TransactionBuilder, TransactionEnvelope
from stellar_sdk.exceptions import NotFoundError

from application.repositories.stellar_repository import StellarRepository
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

    GA_NGNG_ASSET_CODE: str = 'gaNGN'


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


def create_root_account(public_key: Optional[str] = None) -> bool:
    url = 'https://friendbot.stellar.org'
    _response = requests.get(url, params={'addr': public_key})
    return _response.get('success')


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


def make_stellar_transaction(account_1: Account,
                             account_1_keypair: Keypair,
                             account_2_keypair: Keypair,
                             base_fee: int,
                             asset: Asset,
                             amount: Decimal) -> str:

    stellar_transaction = TransactionBuilder(
        source_account=account_1,
        network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    ).append_set_options_op(
        master_weight=1,
        low_threshold=0,
        med_threshold=0,
        high_threshold=3,
    ).append_payment_op(
        destination=account_2_keypair.public_key,
        asset=asset,
        amount=amount
    ).set_timeout(
        settings.DEFAULT_TIMEOUT
    ).build()

    # Sign this transaction with the issuer secret key
    stellar_transaction.sign(account_1_keypair)
    transaction_xdr: str = stellar_transaction.to_xdr()
    return transaction_xdr


def make_transaction():
    server = Server(horizon_url=ConstantsDTO.TESTNET)

    base_fee: int = server.fetch_base_fee()
    issuer_keypair: Keypair = Keypair.from_secret(
        ConstantsDTO.ROOT_ISSUER_SECRET_KEY)
    issuer_account = get_issuer_account(server=server)
    asset = Asset(
        code=ConstantsDTO.GA_NGNG_ASSET_CODE,
        issuer=issuer_keypair.public_key
    )
    # Recipient Account #1 ↓
    account_1: Account = get_or_create_stellar_account(
        server=server,
        recipient_public_key=ConstantsDTO.RECIPIENT_1_PUBLIC_KEY,
        issuer_keypair=issuer_keypair,
        issuer_account=issuer_account,
        base_fee=base_fee,
    )

    # Recipient Account #1 ↑
    account_1_keypair = Keypair.from_secret(
        ConstantsDTO.RECIPIENT_1_SECRET_KEY)

    # Recipient Account #2 ↓
    account_2: Account = get_or_create_stellar_account(
        server=server,
        recipient_public_key=ConstantsDTO.RECIPIENT_2_PUBLIC_KEY,
        issuer_keypair=issuer_keypair,
        issuer_account=issuer_account,
        base_fee=base_fee,
    )

    account_2_keypair = Keypair.from_secret(
        ConstantsDTO.RECIPIENT_2_SECRET_KEY)
    amount = Decimal('555.77')

    transaction_xdr = make_stellar_transaction(
        account_1=account_1,
        account_1_keypair=account_1_keypair,
        account_2_keypair=account_2_keypair,
        base_fee=base_fee,
        asset=asset,
        amount=amount,
    )
    return transaction_xdr


def send_transaction(transaction_xdr: str):
    server = Server(horizon_url=ConstantsDTO.TESTNET)
    account_2_keypair = Keypair.from_secret(ConstantsDTO.RECIPIENT_2_SECRET_KEY)
    transaction = TransactionEnvelope.from_xdr(
        transaction_xdr, network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE)
    # transaction.sign(account_2_keypair.secret)
    response = server.submit_transaction(transaction)
    print(f'{response=}')
    return response


def get_args(args: List, index: int):
    try:
        return args[index]
    except IndexError:
        return None


if __name__ == "__main__":
    args = sys.argv
    command_name = get_args(sys.argv, 1)
    MAKE_TRANSACTION_COMMAND = 'make_transaction'
    SEND_TRANSACTION_COMMAND = 'send_transaction'
    COMMANDS = (MAKE_TRANSACTION_COMMAND, SEND_TRANSACTION_COMMAND)
    if command_name == MAKE_TRANSACTION_COMMAND:
        transaction_xdr = make_transaction()
        print(transaction_xdr)
    elif command_name == SEND_TRANSACTION_COMMAND:
        transaction_xdr = get_args(sys.argv, 2)
        send_transaction(transaction_xdr=transaction_xdr)
    else:
        raise ValueError(
            f'Incorrect command. Available commands:\n{", ".join(COMMANDS)}')
