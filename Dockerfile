FROM python:3.10-slim


ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION=1.1.12

RUN pip install "poetry==$POETRY_VERSION" && apt-get update \
    && apt-get install gnupg -y \
    && apt-get clean 

RUN mkdir /app
WORKDIR /app

COPY poetry.lock pyproject.toml ./

RUN poetry export --without-hashes -f requirements.txt --output requirements.txt \
    && pip install -r requirements.txt --no-cache

ADD . /app/
