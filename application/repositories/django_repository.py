from dataclasses import dataclass
from typing import Dict, Literal, Optional, Union
from requests import Session, Response

from application.schemas import DjangoAuthCredentials, GAStellarAccountSchema
from conf.exceptions import NoMethodFoundError
from conf.settings import settings

from .repository import Repository


@dataclass
class MethodsType:
    GET: str = 'get'
    POST: str = 'post'
    PATCH: str = 'patch'
    DELETE: str = 'delete'


class DjangoRepository(Repository):
    """Django repository class"""

    @staticmethod
    def get_credentials(session: Session, timeout: float) -> DjangoAuthCredentials:
        """Method for initial receipt of pairs of refresh & access tokens"""
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

    @staticmethod
    def get_refreshed_credentials(session: Session,
                                  timeout: float,
                                  access_token: str,
                                  refresh_token: str) -> DjangoAuthCredentials:
        """Method for receiving new pair refresh & access tokens"""
        response = session.post(
            headers={'Authorization': f'Bearer {access_token}'},
            url=f'{settings.DJANGO_DOMAIN}/auth-microservice/refresh/',
            data=dict(refresh_token=refresh_token),
            timeout=timeout
        )
        response.raise_for_status()
        return DjangoAuthCredentials(**response.json())

    @classmethod
    def get_stellar_accounts(session: Session,
                             timeout: float,
                             access_token: str) -> List[GAStellarAccountSchema]:
        """
            Method for retrieving a list of StellarAccount objects from Django-server
        """
        response = session.get(
            url=f'{settings.DJANGO_DOMAIN}/stellar/account-list/',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=timeout
        )
        response.raise_for_status()
        return [GAStellarAccountSchema(**account) for account in response.json()]
