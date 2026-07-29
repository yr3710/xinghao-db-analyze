from sanic import Blueprint, Request

from common.res_decorator import async_json_resp


bp = Blueprint(
    "healthApi",
    url_prefix="/system",
)


@bp.get("/health")
@async_json_resp
async def health(request: Request):
    return {
        "name": "xinghao-db-analyze",
        "status": "running",
    }