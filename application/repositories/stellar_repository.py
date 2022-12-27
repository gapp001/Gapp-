from decimal import Decimal
import requests
from typing import Any, Dict, List, Optional
from stellar_sdk import (Account, Asset, Keypair, Network, Server,
                         TransactionBuilder)
from stellar_sdk.exceptions import (NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError, SignatureExistError)
from stellar_sdk.xdr.transaction_result import TransactionResult
from stellar_sdk.xdr.payment_result_code import PaymentResultCode
from stellar_sdk.decorated_signature import DecoratedSignature
from sentry_sdk import set_context, capture_message


from application.schemas import (GATransactionSchema, StellarPaymentTransactionSchema, StellarWallet, TransactionResultSchema)
from conf.exceptions import NoRecipientAccountFound

from conf.settings import settings
from .repository import Repository


class StellarRepository(Repository):
    """Repository class for Stellar logic"""

    @staticmethod
    def get_network_passphrase() -> str:
        """Returns Stellar network passphrase"""
        if settings.SENTRY_ENV == settings.PROD_SENTRY_ENV:
            return Network.PUBLIC_NETWORK_PASSPHRASE
        return Network.TESTNET_NETWORK_PASSPHRASE


    @staticmethod
    def check_trustline_exists(account_wallets: List[Dict[str, Any]]) -> bool:
        """Method for checking if an account has a trustline"""
        has_ga_ngn_trustline: bool = False
        has_ga_usd_trustline: bool = False
        for wallet in account_wallets:
            if wallet.get('asset_code') == settings.GA_NGN_ASSET_CODE:
                has_ga_ngn_trustline = True
            elif wallet.get('asset_code') == settings.GA_USD_ASSET_CODE:
                has_ga_usd_trustline = True
        return has_ga_ngn_trustline and has_ga_usd_trustline

    @staticmethod
    def get_asset(issuer_public_key: str, currency: str) -> Asset:
        """Method for returning Asset object"""
        match currency:
            case settings.USD_CURRENCY:
                return Asset(settings.GA_USD_ASSET_CODE, issuer_public_key)
            case settings.NGN_CURRENCY:
                return Asset(settings.GA_NGN_ASSET_CODE, issuer_public_key)
            case _:
                raise ValueError('Incorrect currency')

    @staticmethod
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
            set_context('get_account_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.get_account', level='error')
            return None

    """
    создали keypauir

    создаем Stellar аккаунт, когда ему впервые начисляют деньги

    смотрим, что есть транзакция, что деньги есть, находим его StellarAccount

    Микросервис его получает, содаетс аккаунт, начисляет деньги 2люмена, создаем линию доверия, переводим N gaNGN
    ______________________________________________

    gaNGN Начисляется когда деньги пришли из Paystack
    gaNGN Начисляется когда деньги пришли из внутреннего перевода
        
    ______________________________________________

    пока не трогаем ↓
        переводим тому, у кого есть только Keypair
        1 -> 2 деньги
        1 -> переводит в Stellar тоже, но Root аккаунту
    пока не трогаем ↑
    
    
    """

    @staticmethod
    def create_stellar_account(server: Server,
                               recipient_public_key: str,
                               issuer_keypair: Keypair,
                               issuer_account: Account,
                               base_fee: int,
                               network_passphrase: str, ) -> bool:
        """
            Method for creating Stellar Account
            The trustline must be created in the mobile application
        """
        stellar_transaction = (
            TransactionBuilder(
                source_account=issuer_account,
                network_passphrase=network_passphrase,
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
            return response.get('successful')
        except (NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError) as e:
            print(f'{e=}')
            print(f'{e.__dict__=}')
            set_context('create_stellar_account_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.create_stellar_account', level='error')
            return False

    @staticmethod
    def send_transaction(server: Server,
                         amount: str | Decimal,
                         recipient_public_key: str,
                         issuer_keypair: Keypair,
                         issuer_account: Account,
                         base_fee: int,
                         asset: Asset,
                         network_passphrase: str, 
                         ga_transaction_id: int | None = None, ) -> StellarPaymentTransactionSchema:
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
        stellar_transaction = (
            TransactionBuilder(
                source_account=issuer_account,
                network_passphrase=network_passphrase,
                base_fee=base_fee,
            )
            .append_payment_op(
                destination=recipient_public_key,
                asset=asset,
                amount=amount,
            )
            .add_text_memo(str(ga_transaction_id))
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        try:
            # Sign this transaction with the issuer secret key
            stellar_transaction.sign(issuer_keypair)
            # Submit the transaction to the Horizon server.
            response = StellarPaymentTransactionSchema(ga_transaction_id=ga_transaction_id,
                                                       **server.submit_transaction(stellar_transaction))
            return response

        except (NotFoundError, BadRequestError, BadResponseError,
                UnknownRequestError, ConnectionError, SignatureExistError,
                AttributeError, ValueError) as e:
            set_context('send_transaction_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.send_transaction', level='error')
            raise e

    # @staticmethod
    # def send_transaction(transaction: GATransactionSchema,
    #                      server: Server,
    #                      issuing_keypair: Keypair,
    #                      issuer: Account,
    #                      base_fee: int,
    #                      asset: Asset) -> TransactionResultSchema:
    #     '''
    #     Send asset from issuing accout to receiving account.
    #     Основная функция, которая создает, подписывает и отправляет транзакцию в сеть Stellar.
    #     '''
    #     # receiving_keypair = cls.create_stellar_account(
    #     #     receiving_public_key=transaction.related_user.stellar_public_key,
    #     #     server=server,
    #     #     issuing_keypair=issuing_keypair,
    #     #     issuer=issuer,
    #     #     base_fee=base_fee,
    #     #     asset=asset
    #     # )

    #     # Build transaction around payment operation (sending asset to distributor).
    #     # Change network_passphrase to Network.PUBLIC_NETWORK_PASSPHRASE in production.
    #     stellar_transaction = (
    #         TransactionBuilder(
    #             source_account=issuer,
    #             network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
    #             base_fee=base_fee,
    #         )
    #         .append_payment_op(
    #             destination=transaction.related_user.stellar_public_key,
    #             asset=asset,
    #             amount=transaction.amount
    #         )
    #         .set_timeout(settings.DEFAULT_TIMEOUT)
    #         .build()
    #     )

    #     transaction_result = TransactionResultSchema(
    #         transaction_id=transaction.id,
    #         public_key=transaction.related_user.stellar_public_key,
    #         # secret_key=receiving_keypair.secret
    #     )
    #     try:
    #         # Sign this transaction with the issuer secret key
    #         stellar_transaction.sign(issuing_keypair)
    #         # Submit the transaction to the Horizon server.
    #         response = StellarPaymentTransactionSchema(
    #             **server.submit_transaction(stellar_transaction))
    #         transaction_result.stellar_transaction_hash = response.hash
    #         transaction_result.stellar_transaction_status = 200
    #         transaction_result.stellar_transaction_detail = 'Success'
    #     except (BadRequestError, BadResponseError) as e:
    #         transaction_result.stellar_transaction_status = e.status
    #         transaction_result.stellar_transaction_detail = e.detail

    #     return transaction_result

    @staticmethod
    def change_trust_operation(server: Server,
                               recipient_keypair: Keypair,
                               base_fee: int,
                               ga_ngn_asset: Asset,
                               ga_usd_asset: Asset,
                               network_passphrase: str, 
                               ) -> None:
        '''
        Create a trustline between receiving account and issuing account for asset.
        Функция для создания линии доверия между эмитентом и получателем.
        Подразумевается, что линия доверия должна создаваться сразу
        после создании аккаунта и подписываться созданным пользователем.
        '''
        # Fetch the current sequence number for the source account from Horizon.
        recipient_account: Account | None = __class__.get_account(
            server=server, public_key=recipient_keypair.public_key)

        if not recipient_account:
            raise NoRecipientAccountFound

        # Build transaction around trustline operation (creating asset).
        stellar_transaction = (
            TransactionBuilder(
                source_account=recipient_account,
                network_passphrase=network_passphrase,
                base_fee=base_fee,
            )
            .append_change_trust_op(asset=ga_ngn_asset)
            .append_change_trust_op(asset=ga_usd_asset)
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )
        try: 
            stellar_transaction.sign(recipient_keypair)
            result = server.submit_transaction(stellar_transaction)
            return result.get('successful', False)
        except (NotFoundError, BadRequestError, BadResponseError,
                UnknownRequestError, ConnectionError, SignatureExistError,
                AttributeError, ValueError) as e:
            set_context('change_trust_operation_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.change_trust_operation', level='error')
            raise e

    @staticmethod
    def check_transaction_result(result_xdr: str) -> bool:
        """Method for checking result of stellar transaction"""
        try:
            transaction_result = TransactionResult.from_xdr(result_xdr)
            transaction = transaction_result.result.results[0]
            return transaction.tr.payment_result.code == PaymentResultCode.PAYMENT_SUCCESS
        except Exception as e:
            set_context('check_transaction_result_case', value=e.__dict__)
            capture_message('Error in StellarRepository.check_transaction_result', level='error')
            return False

    @staticmethod
    def get_account_balances(raw_data: Dict[str, Any]) -> Dict[str, StellarWallet]:
        """Returns a Dict of StellarWalletBalance objects"""
        return {
            balance.get('asset_code', 'native'): StellarWallet(**balance)
            for balance in raw_data.get('balances')
        }

    @staticmethod
    def compare_balances(stellar_wallet_balance: Decimal, ga_wallet_balance: Decimal):
        """
            Method for comparing balances
            @Returns: bool a parameter indicating whether it is necessary to update the balance of the stellar wallet
        """
        if stellar_wallet_balance >= ga_wallet_balance:
            # Stellar wallet balance not needed for updating 
            return False

        # Stellar wallet balance needed for updating 
        return True

class NoSignaturesFound(Exception):
    ...
