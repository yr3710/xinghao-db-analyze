from sanic import Blueprint, Request
from sanic_ext import openapi

from common.param_parser import parse_params
from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from model.schemas import (
    DataTrainingListResponse,
    DeleteDataTrainingRequest,
    SaveDataTrainingRequest,
    get_schema,
)
from services.data_training_service import (
    create_training,
    delete_training,
    enable_training,
    page_data_training,
    update_training,
)

bp = Blueprint(
    "dataTraining",
    url_prefix="/system/data-training",
)


@bp.get("/page/<page:int>/<size:int>")
@openapi.summary("分页查询训练数据")
@openapi.tag("数据训练")
@openapi.parameter("question", str, description="问题描述")
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(DataTrainingListResponse)
        }
    },
)
@check_token
@async_json_resp
async def page_list(request: Request, page: int, size: int):
    question = request.args.get("question")
    return await page_data_training(page, size, question)


@bp.put("/")
@openapi.summary("创建或更新训练数据")
@openapi.tag("数据训练")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(SaveDataTrainingRequest)
        }
    }
)
@check_token
@async_json_resp
@parse_params
async def save(request: Request, body: SaveDataTrainingRequest):
    if body.id:
        return await update_training(body.model_dump())
    return await create_training(body.model_dump())


@bp.delete("/")
@openapi.summary("删除训练数据")
@openapi.tag("数据训练")
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(DeleteDataTrainingRequest)
        }
    }
)
@check_token
@async_json_resp
@parse_params
async def remove(
    request: Request,
    body: DeleteDataTrainingRequest,
):
    return await delete_training(body.ids)


@bp.get("/<id:int>/enable/<enabled:str>")
@openapi.summary("启用或禁用训练数据")
@openapi.tag("数据训练")
@check_token
@async_json_resp
async def enable(
    request: Request,
    id: int,
    enabled: str,
):
    is_enabled = enabled.lower() == "true"
    return await enable_training(id, is_enabled)
