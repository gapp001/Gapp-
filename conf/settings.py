import logging
import sentry_sdk
from pydantic import BaseSettings


# ↓ Logger initialization ↓
LOGGER = logging.getLogger(__name__)


class Settings(BaseSettings):
    DJANGO_CREDENTIALS_TTL: int  # in minutes

    # Stellar cofigurations
    HORIZON_URL: str
    DEFAULT_TIMEOUT: int
    NGN_CURRENCY = 'NGN'
    USD_CURRENCY = 'USD'
    GA_NGN_ASSET_CODE: str
    GA_USD_ASSET_CODE: str
    ISSUER_SECRET_KEY: str  # Root account
    STARTING_XLM_BALANCE: str  # For new accounts

    # Django API authentication cofigurations
    DJANGO_DOMAIN: str
    STELLAR_MICROSERVICE_LOGIN: str
    STELLAR_MICROSERVICE_PASSWORD: str

    # Celery cofigurations
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    CELERY_TIMEZONE: str

    # Redis cofigurations
    REDIS_HOST: str

    # GPG configurations
    GPG_ROOT_KEY_PASSPHRASE: str
    GPG_ROOT_B64_PUB_KEY: str
    GPG_ROOT_B64_PRIV_KEY: str

    SENTRY_URL: str
    SENTRY_ENV: str

    LOCAL_SENTRY_ENV: str = 'local'
    DEV_SENTRY_ENV: str = 'dev'
    PROD_SENTRY_ENV: str = 'prod'

    class Config:
        env_file = '.env'


settings = Settings()


def configure_sentry():
    """Function for initializing Sentry"""
    if settings.SENTRY_ENV != settings.LOCAL_SENTRY_ENV:
        sentry_sdk.init(
            dsn=settings.SENTRY_URL,
            traces_sample_rate=1.0,
            send_default_pii=True,
            environment=settings.SENTRY_ENV,
        )

def configure_logger():
    """Functuion for initialize Logger"""
    if settings.SENTRY_ENV != settings.PROD_SENTRY_ENV:
        LOGGER.setLevel(logging.DEBUG)
    else:
        LOGGER.setLevel(logging.NOTSET)


def initialize():
    """Function for initialize Sentry, Logger"""

    # ↓ Sentry initialization ↓
    configure_sentry()

    # ↓ Logger initialization ↓
    configure_logger()

# Initializing Sentry, Logger
initialize()