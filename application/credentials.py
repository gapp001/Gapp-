import redis
import requests

from application.schemas import DjangoAuthCredentials
from conf.settings import settings


def get_refreshed_credentials_from_django(session: requests.Session,
                                          timeout: float,
                                          access_token: str,
                                          refresh_token: str) -> DjangoAuthCredentials:
    response = session.post(
        url=f'{settings.DJANGO_DOMAIN}/auth-microservice/refresh/',
        headers={'Authorization': f'Bearer {access_token}'},
        data={'refresh_token': refresh_token},
        timeout=timeout
    )
    response.raise_for_status()
    return DjangoAuthCredentials(**response.json())


def get_credentials_from_django(session: requests.Session, timeout: float) -> DjangoAuthCredentials:
    response = session.post(
        url=f'{settings.DJANGO_DOMAIN}/auth-microservice/auth/',
        data={
            'login': settings.STELLAR_MICROSERVICE_LOGIN,
            'password': settings.STELLAR_MICROSERVICE_PASSWORD
        },
        timeout=timeout
    )
    response.raise_for_status()
    return DjangoAuthCredentials(**response.json())


def set_credentials_into_redis(conn: redis.Redis, credentials: DjangoAuthCredentials):
    with conn.pipeline(transaction=True) as pipe:
        pipe.set('access_token', credentials.access_token)
        pipe.set('refresh_token', credentials.refresh_token)
        pipe.execute()
        pipe.reset()


def get_credentials_from_redis(conn: redis.Redis,
                               session: requests.Session,
                               timeout: float) -> DjangoAuthCredentials:
    access_token = conn.get('access_token')
    refresh_token = conn.get('refresh_token')
    if not access_token:
        credentials = get_credentials_from_django(session=session, timeout=timeout)
        set_credentials_into_redis(conn=conn, credentials=credentials)
        return credentials
    return DjangoAuthCredentials(access_token=access_token, refresh_token=refresh_token)
