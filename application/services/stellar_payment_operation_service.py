from decimal import Decimal
from typing import Any, Dict, Literal
from stellar_sdk import (Account, Asset, Keypair, Server, )
from stellar_sdk.exceptions import (NotFoundError, BadRequestError, BadResponseError, UnknownRequestError, ConnectionError, SignatureExistError)


from application.repositories.stellar_repository import StellarRepository
from application.schemas import ResultDTO
from conf.exceptions import NoIssuerAccountFound
from conf.settings import settings


class StellarPaymentOperationService:
    """Service class for proccessing payment operations in Stellar Network"""

    @staticmethod
    def accural_funds_to_stellar_account(recipient_public_key: str, amount: Decimal, currency: Literal['NGN', 'USD'], ) -> ResultDTO:
        """Method for accruing funds to the Stellar account"""
        if currency not in ('NGN', 'USD',):
            raise ValueError('currency must be "NGN" or "USD"')

        server: Server = Server(settings.HORIZON_URL)
        issuer_keypair = Keypair.from_secret(secret=settings.ISSUER_SECRET_KEY)
        issuer_account: Account | None = StellarRepository.get_account(
            server=server, public_key=issuer_keypair.public_key, )

        if not issuer_account:
            raise NoIssuerAccountFound

        asset: Asset = StellarRepository.get_asset(
            issuer_public_key=issuer_keypair.public_key,
            currency=currency,
        )

        base_fee: int = server.fetch_base_fee()
        network_passphrase: str = StellarRepository.get_network_passphrase()
        try:
            result: Dict[str, Any] = StellarRepository.process_payment_operation(
                server=server,
                amount=amount,
                recipient_public_key=recipient_public_key,
                issuer_keypair=issuer_keypair,
                issuer_account=issuer_account,
                base_fee=base_fee,
                asset=asset,
                network_passphrase=network_passphrase,
                memo=StellarRepository.FORCED_PAYMENT_MEMO,
            )
            return ResultDTO(is_success=result.get('successful') == True)
        except (NotFoundError, BadRequestError) as e:
            return ResultDTO(is_success=False, detail=e.message)
        finally:
            server.close()