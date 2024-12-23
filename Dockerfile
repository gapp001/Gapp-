FROM python:3.10-slim


ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_VERSION=1.5.1

RUN pip install "poetry==$POETRY_VERSION" && apt-get update \
    && apt-get install gnupg -y \
    && apt-get clean 

RUN mkdir /app
WORKDIR /app

ADD . /app/

RUN poetry export --without-hashes -f requirements.txt --output requirements.txt \
    && pip install -r requirements.txt --no-cache

