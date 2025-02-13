# give-away-stellar-microservice

### Local deployment.
```bash 
python3.10 -m venv .venv
source .venv/bin/activate
poetry install
```

* Create a .env file.
* Pull the environment variables into the .env file (an example can be found in .env.example).

### Local startup.
```bash 
celery -A conf worker -l INFO
uvicorn application.main:app --reload
```
