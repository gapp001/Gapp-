from fastapi import Request
from fastapi.routing import APIRouter

from conf.celery import (send_transaction_result_to_django,
                         set_transaction_result_into_redis)


router = APIRouter()


# curl -X GET http://localhost:8000/stellar/run_task/"
@router.get('/run_task/')
async def run_task(request: Request):
    response = send_transaction_result_to_django()
    # response = set_transaction_result_into_redis()
    return response
