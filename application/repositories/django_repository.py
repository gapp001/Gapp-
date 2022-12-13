from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union
from requests import Session, Response, HTTPError

from application.schemas import DjangoAuthCredentials, GAStellarAccountSchema, GATransactionSchema
from conf.settings import settings
from application.choices import StellarTransactionStatus, TransactionStatus, TransactionKind
from .repository import Repository
from sentry_sdk import set_context, capture_message


class DjangoRepository(Repository):
    """Django repository class"""

    @staticmethod
    def get_credentials(session: Session, timeout: float) -> DjangoAuthCredentials:
        """Method for initial receipt of pairs of refresh & access tokens"""
        try:
            response = session.post(
                url=f'{settings.DJANGO_DOMAIN}/auth-microservice/auth/',
                data=dict(
                    login=settings.STELLAR_MICROSERVICE_LOGIN,
                    password=settings.STELLAR_MICROSERVICE_PASSWORD
                ),
                timeout=timeout
            )

            response.raise_for_status()
            return DjangoAuthCredentials(**response.json())
        except HTTPError as e:
            set_context('get_credentials_case', value=e.__dict__)
            capture_message('Error in DjangoRepository.get_credentials', level='error')

    @staticmethod
    def get_refreshed_credentials(session: Session,
                                  timeout: float,
                                  access_token: str,
                                  refresh_token: str) -> DjangoAuthCredentials:
        """Method for receiving new pair refresh & access tokens"""
        try:
            response = session.post(
                headers={'Authorization': f'Bearer {access_token}'},
                url=f'{settings.DJANGO_DOMAIN}/auth-microservice/refresh/',
                data=dict(refresh_token=refresh_token),
                timeout=timeout
            )
            response.raise_for_status()
            return DjangoAuthCredentials(**response.json())
        except HTTPError as e:
            set_context('get_refreshed_credentials_case', value=e.__dict__)
            capture_message('Error in DjangoRepository.get_refreshed_credentials', level='error')

    @staticmethod
    def get_stellar_accounts(session: Session,
                             timeout: float,
                             access_token: str) -> List[GAStellarAccountSchema]:
        """
            Method for retrieving a list of StellarAccount objects from Django-server
            The status of Stellar-accounts is "keypair_generated"
        """
        try:
            response = session.get(
                url=f'{settings.DJANGO_DOMAIN}/stellar/account-list/',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=timeout
            )
            response.raise_for_status()
            return [GAStellarAccountSchema(**account) for account in response.json()]
        except HTTPError as e:
            set_context('get_stellar_accounts_case', value=e.__dict__)
            capture_message('Error in DjangoRepository.get_stellar_accounts', level='error')

    def send_updated_stellar_accounts(session: Session,
                                      timeout: float,
                                      access_token: str, data: List[Dict[str, Any]]) -> int:
        """
            Method for sending a list of StellarAccount objects with updated statuses to Django-server
        """
        try:
            response = session.post(
                url=f'{settings.DJANGO_DOMAIN}/stellar/account-list/update-status/',
                json=data,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=timeout
            )
            response.raise_for_status()
            return response.status_code
        except HTTPError as e:
            set_context('send_updated_stellar_accounts_case', value=e.__dict__)
            capture_message(
                'Error in DjangoRepository.send_updated_stellar_accounts', level='error')

    def get_transactions(session: Session,
                         timeout: float,
                         access_token: str) -> List[GATransactionSchema]:
        """
            Method for retrieving transactions list with transaction.status is "in_processing" 
            and transaction.stellar_status is "unconfirmed"
        """
        try:
            response = session.get(
                url=f'{settings.DJANGO_DOMAIN}/transactions/stellar/',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=timeout
            )
            response.raise_for_status()
            return [GATransactionSchema(**transaction) for transaction in response.json()]
        except HTTPError as e:
            set_context('get_transactions_from_django_case', value=e.__dict__)
            capture_message(
                'Error in DjangoRepository.get_transactions', level='error')
