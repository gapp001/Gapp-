from fastapi import FastAPI

from application.routers import router
from conf.settings import settings


app = FastAPI()
app.include_router(router=router, prefix=settings.APP_PREFIX)

# uvicorn application.main:app --reload
