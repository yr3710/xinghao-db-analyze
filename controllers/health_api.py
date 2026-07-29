from pydantic import BaseModel
from sanic import Blueprint, Request

from common.param_parser import parse_params
from common.res_decorator import async_json_resp


bp = Blueprint(
    "healthApi",
    url_prefix="/system",
)


class EchoRequest(BaseModel):
    query: str
    count: int = 1


@bp.get("/health")
@async_json_resp
async def health(request: Request):
    return {
        "name": "xinghao-db-analyze",
        "status": "running",
    }


@bp.post("/echo")
@async_json_resp
@parse_params
async def echo(
    request: Request,
    body: EchoRequest,
):
    return body.model_dump()


@bp.get("/add")
@async_json_resp
@parse_params
async def add(
    request: Request,
    number_a: int,
    number_b: int,
):
    return {
        "result": number_a + number_b,
    }