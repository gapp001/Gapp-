from decimal import Decimal
import unittest
from application.schemas import ResultDTO

from conf.settings import settings
from application.services.stellar_payment_operation_service import StellarPaymentOperationService


class StellarPaymentOperationServiceTestCase(unittest.TestCase):
    """StellarPaymentOperationService Test Case"""

    def setUp(self) -> None:
        self.service = StellarPaymentOperationService()
    
    def test_accural_ga_usd(self):
        """Accural gaUSD asset to Stellar Account"""
        recipient_public_key: str = 'GCPO7M5CB4M46HSC5NAIV34MRKT77UZPWTN6FSBCMGFPF4UVRK7TJF55'
        currency: str = settings.USD_CURRENCY
        amount: Decimal = Decimal('10.00')
        result_dto: ResultDTO = self.service.accural_funds_to_stellar_account(recipient_public_key=recipient_public_key, currency=currency, amount=amount)
        self.assertTrue(result_dto.is_success, msg=result_dto.detail)

    def test_accural_ga_ngn(self):
        """Accural gaNGN asset to Stellar Account"""
        recipient_public_key: str = 'GCPO7M5CB4M46HSC5NAIV34MRKT77UZPWTN6FSBCMGFPF4UVRK7TJF55'
        currency: str = settings.NGN_CURRENCY
        amount: Decimal = Decimal('500.00')
        result_dto: ResultDTO = self.service.accural_funds_to_stellar_account(recipient_public_key=recipient_public_key, currency=currency, amount=amount)
        self.assertTrue(result_dto.is_success, msg=result_dto.detail)

