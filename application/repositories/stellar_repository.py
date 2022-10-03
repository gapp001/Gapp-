import requests
from typing import Any, Dict, Optional
from stellar_sdk import (Account, Asset, Keypair, Network, Server,
                         TransactionBuilder)
from stellar_sdk.exceptions import BadRequestError, BadResponseError
from stellar_sdk.exceptions import NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError

from application.schemas import (
    GATransactionSchema, StellarPaymentTransactionSchema, TransactionResultSchema)
from conf.settings import settings
from .repository import Repository


class StellarRepository(Repository):
    """Repository class for Stellar logic"""

    def create_root_account(public_key: Optional[str] = None) -> bool:
        """
            USE ONLY FOR DEBUG ↓
                Function for creating root account
            USE ONLY FOR DEBUG ↑
        """
        url = 'https://friendbot.stellar.org'
        response = requests.get(url, params={'addr': public_key})
        response.raise_for_status()
        return response.get('success')

    @staticmethod
    def get_account(server: Server, public_key: str) -> Account | None:
        """Method for rertieving account by his public_key`"""
        try:
            return server.load_account(public_key)
        except NotFoundError as e:
            # TODO Add sentry catching error
            return None

    @staticmethod
    def create_stellar_account(server: Server,
                               recipient_public_key: str,
                               issuer_keypair: Keypair,
                               issuer_account: Account,
                               base_fee: int) -> bool:
        """
            Method for creating Stellar Account
            The trustline must be created in the mobile application
        """
        stellar_transaction = (
            TransactionBuilder(
                source_account=issuer_account,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=base_fee,
            )
            .append_create_account_op(
                destination=recipient_public_key,
                starting_balance=settings.STARTING_XLM_BALANCE
            )
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        stellar_transaction.sign(issuer_keypair)
        try:
            response: Dict[str, Any] = server.submit_transaction(
                stellar_transaction)
            # Create trustline between issuer and receiver (for test)
            # This action will be complete in the Mobile app
            # ↓ DEPRECATED ↓
            # cls.change_trust_operation(
            #     server, receiving_keypair, base_fee, asset)
            # ↑ DEPRECATED ↑
            return response.get('successful')
        except (NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError) as e:
            # TODO Add sentry catching error
            return False

    @staticmethod
    def send_transaction(transaction: GATransactionSchema,
                         server: Server,
                         issuing_keypair: Keypair,
                         issuer: Account,
                         base_fee: int,
                         asset: Asset) -> TransactionResultSchema:
        '''
        Send asset from issuing accout to receiving account.
        Основная функция, которая создает, подписывает и отправляет транзакцию в сеть Stellar.
        '''
        # receiving_keypair = cls.create_stellar_account(
        #     receiving_public_key=transaction.related_user.stellar_public_key,
        #     server=server,
        #     issuing_keypair=issuing_keypair,
        #     issuer=issuer,
        #     base_fee=base_fee,
        #     asset=asset
        # )

        # Build transaction around payment operation (sending asset to distributor).
        # Change network_passphrase to Network.PUBLIC_NETWORK_PASSPHRASE in production.
        stellar_transaction = (
            TransactionBuilder(
                source_account=issuer,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=base_fee,
            )
            .append_payment_op(
                destination=transaction.related_user.stellar_public_key,
                asset=asset,
                amount=transaction.amount
            )
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        transaction_result = TransactionResultSchema(
            transaction_id=transaction.id,
            public_key=transaction.related_user.stellar_public_key,
            # secret_key=receiving_keypair.secret
        )
        try:
            # Sign this transaction with the issuer secret key
            stellar_transaction.sign(issuing_keypair)
            # Submit the transaction to the Horizon server.
            response = StellarPaymentTransactionSchema(
                **server.submit_transaction(stellar_transaction))
            transaction_result.stellar_transaction_hash = response.hash
            transaction_result.stellar_transaction_status = 200
            transaction_result.stellar_transaction_detail = 'Success'
        except (BadRequestError, BadResponseError) as e:
            transaction_result.stellar_transaction_status = e.status
            transaction_result.stellar_transaction_detail = e.detail

        return transaction_result

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
