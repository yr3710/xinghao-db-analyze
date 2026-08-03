from sanic import Blueprint, Request
from sanic.response import ResponseStream

from common.param_parser import parse_params
from common.token_decorator import check_token
from common.res_decorator import async_json_resp
from model.schemas import (
    LLMGetAnswerRequest,
    StopChatRequest,
)
from services.llm_service import (
    llm_request,
    stop_dify_chat,
)

bp = Blueprint(
    "difyApi",
    url_prefix="/dify",
)


@bp.post("/get_answer")
@check_token
@parse_params
async def get_answer(
    request: Request,
    body: LLMGetAnswerRequest,
):
    token = request.headers.get("Authorization")

    if token.startswith("Bearer "):
        token = token.removeprefix("Bearer ")

    request_data = body.model_dump()

    async def stream_fn(response):
        await llm_request.exec_query(
            response=response,
            req_obj=request_data,
            token=token,
        )

    return ResponseStream(
        stream_fn,
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@bp.post("/stop_chat")
@check_token
@async_json_resp
@parse_params
async def stop_chat(
    request: Request,
    body: StopChatRequest,
):
    return await stop_dify_chat(
        request=request,
        task_id=body.task_id,
        qa_type=body.qa_type,
    )