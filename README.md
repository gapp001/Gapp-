# give-away-stellar-microservice

### Локальное развертывание
```bash 
python3.10 -m venv .venv
source .venv/bin/activate
poetry install
```

* Cоздать .env файл
* Подтянуть переменные виртуального окружения в .env файл (пример находится в .env.example)

### Локальный запуск
```bash 
celery -A conf worker -l INFO
uvicorn application.main:app --reload
```
