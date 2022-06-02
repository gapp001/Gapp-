from pydantic import BaseSettings


class Settings(BaseSettings):
    # FastAPI cofigurations
    APP_PREFIX: str

    # Stellar cofigurations
    HORIZON_URL: str
    DEFAULT_TIMEOUT: int
    ASSET_CODE: str
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

    class Config:
        env_file = '.env'


settings = Settings()
