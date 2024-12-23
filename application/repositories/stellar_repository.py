from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
from sentry_sdk import capture_message, set_context
from stellar_sdk import (Account, Asset, Keypair, Network, Server, TextMemo,
                         TransactionBuilder, TransactionEnvelope)
from stellar_sdk.decorated_signature import DecoratedSignature
from stellar_sdk.exceptions import (BadRequestError, BadResponseError,
                                    ConnectionError, NotFoundError,
                                    SignatureExistError, UnknownRequestError)
from stellar_sdk.xdr.inner_transaction_result import InnerTransactionResult
from stellar_sdk.xdr.inner_transaction_result_pair import \
    InnerTransactionResultPair
from stellar_sdk.xdr.inner_transaction_result_result import \
    InnerTransactionResultResult
from stellar_sdk.xdr.operation_result import OperationResult
from stellar_sdk.xdr.payment_result_code import PaymentResultCode
from stellar_sdk.xdr.transaction_result import TransactionResult
from stellar_sdk.xdr.transaction_result_result import TransactionResultResult

from application.schemas import (GATransactionSchema,
                                 StellarPaymentTransactionSchema,
                                 StellarWallet, TransactionResultSchema)
from conf.exceptions import NoRecipientAccountFound
from conf.settings import LOGGER, settings

from .repository import Repository


class StellarRepository(Repository):
    """Repository class for Stellar logic"""

    FORCED_PAYMENT_MEMO = TextMemo(text='forced_payment')


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
                'Error in StellarRepository.get_account', level='error'
            )
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
    def create_stellar_account(
        server: Server,
        recipient_public_key: str,
        issuer_keypair: Keypair,
        issuer_account: Account,
        base_fee: int,
        network_passphrase: str,
    ) -> bool:
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
                starting_balance=settings.STARTING_XLM_BALANCE,
            )
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        stellar_transaction.sign(issuer_keypair)
        try:
            response: Dict[str, Any] = server.submit_transaction(
                stellar_transaction
            )
            return response.get('successful')
        except (
            NotFoundError,
            BadRequestError,
            BadResponseError,
            UnknownRequestError,
            ConnectionError,
        ) as e:
            print(f'{e=}')
            print(f'{e.__dict__=}')
            set_context('create_stellar_account_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.create_stellar_account',
                level='error',
            )
            return False

    @staticmethod
    def send_transaction(
        server: Server,
        amount: str | Decimal,
        recipient_public_key: str,
        issuer_keypair: Keypair,
        issuer_account: Account,
        base_fee: int,
        asset: Asset,
        network_passphrase: str,
        ga_transaction_id: int | None = None,
    ) -> StellarPaymentTransactionSchema:
        """Send asset from issuing accout to receiving account"""

        try:
            stellar_response: Dict[str, Any] = __class__.process_payment_operation(
                server=server,
                amount=amount,
                recipient_public_key=recipient_public_key,
                issuer_keypair=issuer_keypair,
                issuer_account=issuer_account,
                base_fee=base_fee,
                asset=asset,
                network_passphrase=network_passphrase,
                memo=TextMemo(text=str(ga_transaction_id)),
            )

            response = StellarPaymentTransactionSchema(
                ga_transaction_id=ga_transaction_id, **stellar_response
            )
            return response

        except (
            NotFoundError,
            BadRequestError,
            BadResponseError,
            UnknownRequestError,
            ConnectionError,
            SignatureExistError,
            AttributeError,
            ValueError,
        ) as e:
            set_context('send_transaction_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.send_transaction', level='error'
            )
            raise e

    @staticmethod
    def process_payment_operation(
        server: Server,
        amount: str | Decimal,
        recipient_public_key: str,
        issuer_keypair: Keypair,
        issuer_account: Account,
        base_fee: int,
        asset: Asset,
        network_passphrase: str,
        memo: TextMemo,
    ) -> Dict[str, Any]:
        """
        Method for processing payment operation to Stellar Network
        @Args:
            server: stellar_sdk.Server,
            amount: str | Decimal,
            recipient_public_key: str,
            issuer_keypair: stellar_sdk.Keypair,
            issuer_account: stellar_sdk.Account,
            base_fee: int,
            asset: stellar_sdk.Asset,
            network_passphrase: str,
            memo: stellar_sdk.TextMemo,

        @Raised:
            NotFoundError,
            BadRequestError,
            BadResponseError,
            UnknownRequestError,
            ConnectionError,
            SignatureExistError,
            AttributeError,
            ValueError

        @Returns: Dict[str, Any] like a format
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
                'valid_before': datetime.datetime(2023, 10, 4, 11, 15, 46, tzinfo = datetime.timezone.utc)
            }
        """
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
            .add_memo(memo=memo)
            .set_timeout(settings.DEFAULT_TIMEOUT)
            .build()
        )

        try:
            # Sign this transaction with the issuer secret key
            stellar_transaction.sign(issuer_keypair)
            # Submit the transaction to the Horizon server.
            response: Dict[str, Any] = server.submit_transaction(
                stellar_transaction
            )
            return response

        except (
            NotFoundError,
            BadRequestError,
            BadResponseError,
            UnknownRequestError,
            ConnectionError,
            SignatureExistError,
            AttributeError,
            ValueError,
        ) as e:
            set_context('send_transaction_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.send_transaction', level='error'
            )
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
    def change_trust_operation(
        server: Server,
        recipient_keypair: Keypair,
        base_fee: int,
        ga_ngn_asset: Asset,
        ga_usd_asset: Asset,
        network_passphrase: str,
    ) -> None:
        """
        Create a trustline between receiving account and issuing account for asset.
        Функция для создания линии доверия между эмитентом и получателем.
        Подразумевается, что линия доверия должна создаваться сразу
        после создании аккаунта и подписываться созданным пользователем.
        """
        # Fetch the current sequence number for the source account from Horizon.
        recipient_account: Account | None = __class__.get_account(
            server=server, public_key=recipient_keypair.public_key
        )

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
        except (
            NotFoundError,
            BadRequestError,
            BadResponseError,
            UnknownRequestError,
            ConnectionError,
            SignatureExistError,
            AttributeError,
            ValueError,
        ) as e:
            set_context('change_trust_operation_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.change_trust_operation',
                level='error',
            )
            raise e

    @staticmethod
    def check_transaction_result(result_xdr: str) -> bool:
        """Method for checking result of stellar transaction"""
        try:

            transaction_result: TransactionResult = TransactionResult.from_xdr(
                result_xdr
            )
            result: TransactionResultResult = transaction_result.result
            transaction: Optional[OperationResult] = None

            if result.results:
                transaction = result.results[0]
            if not result.results and result.inner_result_pair:
                inner_result_pair: InnerTransactionResultPair = (
                    result.inner_result_pair
                )
                inner_result: InnerTransactionResult = inner_result_pair.result
                inner_result_result: InnerTransactionResultResult = (
                    inner_result.result
                )
                transaction = inner_result_result.results[0]

            if not transaction:
                print('Not valid processing transaction result')
                return False

            return (
                transaction.tr.payment_result.code
                == PaymentResultCode.PAYMENT_SUCCESS
            )
        except Exception as e:
            set_context('check_transaction_result_case', value=e.__dict__)
            capture_message(
                'Error in StellarRepository.check_transaction_result',
                level='error',
            )
            return False

    @staticmethod
    def get_account_balances(
        raw_data: Dict[str, Any]
    ) -> Dict[str, StellarWallet]:
        """Returns a Dict of StellarWalletBalance objects"""
        return {
            balance.get('asset_code', 'native'): StellarWallet(**balance)
            for balance in raw_data.get('balances')
        }

    @staticmethod
    def compare_balances(
        stellar_wallet_balance: Decimal, ga_wallet_balance: Decimal
    ):
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
