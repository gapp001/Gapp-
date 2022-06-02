from typing import List

import requests
from stellar_sdk import (Account, Asset, Keypair, Network, Server,
                         TransactionBuilder)
from stellar_sdk.exceptions import BadRequestError, BadResponseError

from application.choices import (StellarStatus, TransactionKind,
                                 TransactionStatus)
from application.schemas import (GATransactionSchema, GAUserSchema,
                                 StellarPaymentTransactionSchema)
from conf.settings import settings


def get_transactions_from_django(session: requests.Session,
                                 timeout: float,
                                 access_token: str) -> List[GATransactionSchema]:
    '''
    Функция получения списка транзакций из give_away django api.
    '''
    response = session.get(
        url=f'{settings.DJANGO_DOMAIN}/transaction/',
        headers={'Authorization': f'Bearer {access_token}'},
        params={
            'stellar_status': StellarStatus.UNCONFIRMED,
            'transaction_status': TransactionStatus.IN_PROCESSING,
            'kind': TransactionKind.GENESIS,
            'has_stellar_transaction_hash': False
        },
        timeout=timeout
    )
    response.raise_for_status()
    return [GATransactionSchema(**transaction) for transaction in response.json()]


def change_trust_operation(server: Server,
                           receiving_keypair: Keypair,
                           base_fee: int,
                           asset: Asset) -> None:
    '''
    Create a trustline between receiving account and issuing account for asset.
    Функция для создания линии доверия между эмитентом и получателем.
    Подразумевается, что линия доверия должна создаваться сразу
    после создании аккаунта и подписываться созданным пользователем.
    '''
    # Fetch the current sequence number for the source account from Horizon.
    receiver = server.load_account(receiving_keypair.public_key)

    # Build transaction around trustline operation (creating asset).
    stellar_transaction = (
        TransactionBuilder(
            source_account=receiver,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        .append_change_trust_op(asset=asset)
        .set_timeout(settings.DEFAULT_TIMEOUT)
        .build()
    )

    stellar_transaction.sign(receiving_keypair)
    server.submit_transaction(stellar_transaction)
    return None


def get_or_create_stellar_account(related_user: GAUserSchema,
                                  server: Server,
                                  issuing_keypair: Keypair,
                                  issuer: Account,
                                  base_fee: int,
                                  asset: Asset) -> str:
    '''
    Проверяем, есть ли у получателя публичный ключ Stellar.
    Если нет, то создаем для получаетля новый аккаунт,
    пополняем его и создаем линию доверия к нашему активу gaNGN.
    '''
    # TODO: Реализовать сохранение публичного и зашифрованного секретного ключей пользователя в бд
    receiving_public_key = related_user.stellar_public_key
    if not receiving_public_key:
        receiving_keypair = Keypair.random()
        stellar_transaction = (
            TransactionBuilder(
                source_account=issuer,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=base_fee,
            )
            .append_create_account_op(
                destination=receiving_keypair.public_key,
                starting_balance=settings.STARTING_XLM_BALANCE
            )
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        stellar_transaction.sign(issuing_keypair)
        server.submit_transaction(stellar_transaction)
        # Create trustline between issuer and receiver (for test)
        change_trust_operation(server, receiving_keypair, base_fee, asset)
        receiving_public_key = receiving_keypair.public_key
    return receiving_public_key


def send_transaction_to_stellar(transaction: GATransactionSchema,
                                server: Server,
                                issuing_keypair: Keypair,
                                issuer: Account,
                                base_fee: int,
                                asset: Asset) -> GATransactionSchema:
    '''
    Send asset from issuing accout to receiving account.
    Основная функция, которая создает, подписывает и отправляет транзакцию в сеть Stellar.
    '''
    receiving_public_key = get_or_create_stellar_account(
        related_user=transaction.related_user,
        server=server,
        issuing_keypair=issuing_keypair,
        issuer=issuer,
        base_fee=base_fee,
        asset=asset
    )

    # Build transaction around payment operation (sending asset to distributor).
    # Change network_passphrase to Network.PUBLIC_NETWORK_PASSPHRASE in production.
    stellar_transaction = (
        TransactionBuilder(
            source_account=issuer,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        .append_payment_op(
            destination=receiving_public_key,
            asset=asset,
            amount=transaction.amount
        )
        .set_timeout(settings.DEFAULT_TIMEOUT)
        .build()
    )

    try:
        # Sign this transaction with the issuer secret key
        stellar_transaction.sign(issuing_keypair)
        # Submit the transaction to the Horizon server.
        response = StellarPaymentTransactionSchema(**server.submit_transaction(stellar_transaction))
        transaction.related_user.stellar_public_key = receiving_public_key
        transaction.stellar_status = StellarStatus.CONFIRMED
        transaction.stellar_transaction_hash = response.hash
        transaction.stellar_transaction_status = 200
        transaction.stellar_transaction_detail = 'Success'
    except (BadRequestError, BadResponseError) as e:
        transaction.stellar_transaction_status = e.status
        transaction.stellar_transaction_detail = e.detail

    return transaction
